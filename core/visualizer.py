import pprint

import utility as util

def visualize_scan_results(hosts: dict, outfile: str):
    print(util.BRIGHT_BLUE + "Results:" + util.SANE)
    pprint.pprint(hosts)
    with open(outfile, "w") as file:
        pprint.pprint(hosts, stream=file)
    print()

def host_details_to_html(filepath: str, hosts: list):
    with open(filepath, "w") as output:
        output.write(""" \
            <html>
                <head>
                    <title>Scan Results</title>
                    <style>
                        table, th, td {
                            border: 1px solid black;
                            border-collapse: collapse;
                        }
                    </style>
                </head>
            <body>""")

        # <table style="width:100%">
        #   <tr>
        #     <th>Name:</th>
        #     <td>Bill Gates</td>
        #   </tr>
        #   <tr>
        #     <th rowspan="2">Telephone:</th>
        #     <td>55577854</td>
        #   </tr>
        #   <tr>
        #     <td>55577855</td>
        #   </tr>
        # </table>

        # for host in hosts:
        #     output.write("""\
        #         <table>")