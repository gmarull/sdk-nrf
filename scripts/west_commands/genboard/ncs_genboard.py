# Copyright (c) 2024 Nordic Semiconductor ASA
# SPDX-License-Identifier: LicenseRef-Nordic-5-Clause

from pathlib import Path
import re
import shutil

from jinja2 import Environment, FileSystemLoader
from west.commands import WestCommand
from west import log
from yaml import load
try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader


SCRIPT_DIR = Path(__file__).absolute().parent
TEMPLATE_DIR = SCRIPT_DIR / "templates"
CONFIG = SCRIPT_DIR / "config.yml"

NCS_VERSION_MIN = (2, 0, 0)
HWMV2_SINCE = (2, 6, 99)

NCS_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
VENDOR_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
BOARD_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


class NcsGenboard(WestCommand):

    def __init__(self):
        super().__init__(
            "ncs-genboard", "Generate board skeleton files for any Nordic SoC", ""
        )

    def do_add_parser(self, parser_adder):
        parser = parser_adder.add_parser(
            self.name, help=self.help, description=self.description
        )

        parser.add_argument(
            "-o", "--output", required=True, type=Path, help="Output directory"
        )
        parser.add_argument("-e", "--vendor", required=True, help="Vendor name")
        parser.add_argument("-b", "--board", required=True, help="Board name")
        parser.add_argument("-d", "--board-desc", required=True, help="Board description")
        parser.add_argument("-s", "--soc", required=True, help="SoC")
        parser.add_argument("-v", "--variant", required=True, help="Variant")
        parser.add_argument(
            "-n", "--ncs-version", required=True, help="NCS target version"
        )

        return parser

    def do_run(self, args, unknown_args):
        with open(CONFIG, "r") as f:
            config = load(f, Loader=Loader)

        # validate input
        m = NCS_VERSION_RE.match(args.ncs_version)
        if not m:
            log.err(f"Invalid NCS version: {args.ncs_version}")
            return

        ncs_version = tuple(int(n) for n in m.groups())

        if ncs_version < NCS_VERSION_MIN:
            log.err(f"Unsupported NCS version: {args.ncs_version}")
            return

        if not VENDOR_RE.match(args.vendor):
            log.err(f"Invalid vendor name: {args.vendor}")
            return
        
        if not BOARD_RE.match(args.board):
            log.err(f"Invalid board name: {args.board}")
            return

        series = None
        for product in config["products"]:
            for soc in product["socs"]:
                if args.soc == soc["name"]:
                    series = product["series"]
                    break

        if not series:
            log.err(f"Invalid/unsupported SoC: {args.soc}")
            return

        ram = None
        flash = None
        for variant in soc["variants"]:
            if args.variant == variant["name"]:
                ram = variant["ram"]
                flash = variant["flash"]
                break
    
        if not ram or not flash:
            log.err(f"Invalid/unsupported variant: {args.variant}")
            return

        # prepare Jinja environment
        env = Environment(
            trim_blocks=True,
            lstrip_blocks=True,
            loader=FileSystemLoader(TEMPLATE_DIR / series),
        )

        env.globals["ncs_version"] = ncs_version
        env.globals["hwmv2_since"] = HWMV2_SINCE
        env.globals["vendor"] = args.vendor
        env.globals["board"] = args.board
        env.globals["board_desc"] = args.board_desc
        env.globals["series"] = series
        env.globals["soc"] = args.soc
        env.globals["variant"] = args.variant
        env.globals["ram"] = ram
        env.globals["flash"] = flash

        # render templates/copy files
        if ncs_version < HWMV2_SINCE:
            out_dir = args.output / "arm" / args.board
        else:
            out_dir = args.output / args.vendor / args.board
    
        if not out_dir.exists():
            out_dir.mkdir(parents=True)

        tmpl = TEMPLATE_DIR / series / "board-pinctrl.dtsi"
        shutil.copy(tmpl, out_dir / f"{ args.board }-pinctrl.dtsi")

        tmpl = TEMPLATE_DIR / series / "pre_dt_board.cmake"
        shutil.copy(tmpl, out_dir)

        tmpl = env.get_template("board_defconfig.jinja2")
        with open(out_dir / f"{ args.board }_defconfig", "w") as f:
            f.write(tmpl.render())

        tmpl = env.get_template("board.cmake.jinja2")
        with open(out_dir / "board.cmake", "w") as f:
            f.write(tmpl.render())

        tmpl = env.get_template("board.dts.jinja2")
        with open(out_dir / f"{args.board}.dts", "w") as f:
            f.write(tmpl.render())

        tmpl = env.get_template("Kconfig.board.jinja2")
        fname = "Kconfig.board" if ncs_version < HWMV2_SINCE else f"Kconfig.{args.board}"
        with open(out_dir / fname, "w") as f:
            f.write(tmpl.render())

        tmpl = env.get_template("Kconfig.defconfig.jinja2")
        with open(out_dir / f"Kconfig.defconfig", "w") as f:
            f.write(tmpl.render())

        tmpl = env.get_template("board_twister.yml.jinja2")
        with open(out_dir / f"{args.board}.yml", "w") as f:
            f.write(tmpl.render())

        if ncs_version >= HWMV2_SINCE:
            tmpl = env.get_template("board.yml.jinja2")
            with open(out_dir / f"board.yml", "w") as f:
                f.write(tmpl.render())
