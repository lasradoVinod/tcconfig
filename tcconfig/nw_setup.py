from email.mime import base
from re import T
import signal
import re
import sys
import json 
import msgfy
import asyncio
from loguru import logger
import argparse
import humanreadable as hr
import time

from textwrap import dedent

from typing import Optional
from tcconfig._importer import set_tc_from_file
from tcconfig.tcdel import main as delmain
from tcconfig.tcshow import main as showmain
from ._const import TrafficDirection,TcCommandOutput


def parse_option():
    parser =  argparse.ArgumentParser(
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description="Wrapper over tcconfig",
            epilog=dedent(
                """\
                tcconfig: https://tcconfig.rtfd.io/
                Documentation: https://docs.google.com/document/d/15WIX_6HV-y5PIF8B4cvZwLTgplHVo_xs_Tl7pyV6JZE/edit
                """
            ),
        )
    
    parser.add_argument("config_file", nargs="?", help="Path to config file")
    parser.add_argument("--loop_forever",help="Continue cycling through the conditions",action="store_true",default=False,required=False)
    parser.add_argument("--export-log", dest="export_path", help="export debug logs to file", default = "", required=False)

    return parser.parse_args()

class NWSetup ():
    def __init__ (self, options):
        self.__event_loop = asyncio.get_event_loop()
        signal.signal(signal.SIGINT, self.signal_handler)
        return
    
    def signal_handler (self, sig, frame):
        self.__event_loop.stop()
        delmain(["lo", "--all"])
        exit()

    def parse(self,config_file):
        from voluptuous import ALLOW_EXTRA, Any, Required, Schema

        schema = Schema(
            {Required(str): { "conditions": {Required(str):{Any(*TrafficDirection.LIST): {str: {str: Any(str, int, float)}}}}},"timing":{int:{str:str}}},
            extra=ALLOW_EXTRA,
        )

        with open(config_file, encoding="utf-8") as fp:
            self.__config_table = json.load(fp)

        schema(self.__config_table)
        
    def event_handler(self,plan_name, idx, plan_table,loop_forever):
        plan_id, timing = next(iter(plan_table["timing"][idx].items()))
        print ("{}, {}".format(int(time.time()*1000), plan_id))
        filename = '/tmp/data' + plan_name + plan_id+'.json'
        with open(filename, 'w') as f:
            json.dump(plan_table["conditions"][plan_id], f)
        set_tc_from_file(logger,filename,False, TcCommandOutput.NOT_SET,True)
        loop = asyncio.get_running_loop()
        timing = hr.Time(timing, hr.Time.Unit.SECOND).seconds
        key_list = sorted(plan_table["timing"].keys())
        idx_new = key_list[(key_list.index(idx)+1) % len(key_list)]
        if (not loop_forever) and idx_new < idx:
            delmain(["lo", "--all"])
            exit()
        loop.call_later(timing,self.event_handler,plan_name,idx_new,plan_table,loop_forever)


    def run(self, loop_forever=bool):
        for plan, plan_table in self.__config_table.items():
            if plan_table is None:
                continue
            base_plan_idx = sorted(plan_table["timing"].keys())[0]
            self.__event_loop.call_soon(self.event_handler,plan,base_plan_idx,plan_table,loop_forever)

        self.__event_loop.run_forever()

            

def main():
    options = parse_option()

    setup = NWSetup(options)
    try:
        setup.parse(options.config_file)
    except OSError as e:
        print(msgfy.to_error_message(e))
        return -1
    except json.decoder.JSONDecodeError as e:
        print(msgfy.to_error_message(e))
        return -1

    try:
        setup.run(options.loop_forever)
    except Exception as e:
        print(msgfy.to_error_message(e))
        return -1

if __name__ == "__main__":
    sys.exit(main())