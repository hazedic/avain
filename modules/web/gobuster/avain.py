import datetime
import logging
import os
import socket
import subprocess
import requests


from core.result_types import ResultType
import core.utility as util

INTERMEDIATE_RESULTS = {ResultType.SCAN: {}}  # get the current scan result
CONFIG = {}
LOGGER = None
VERBOSE = False
CREATED_FILES = ["gobuster_out.txt"]

TARGETS = []  # list targets as (ip, host, port, service)
EXCLUDE_DIRS = set()

def run(results: list):
    """
    Entry point for this module.
    """

    global LOGGER, EXCLUDE_DIRS

    # setup logger
    LOGGER = logging.getLogger(__name__)
    LOGGER.info("Starting with gobuster scan")

    set_targets()
    webserver_map = {}
    EXCLUDE_DIRS = set([x.strip() for x in CONFIG.get("exclude_dirs", "").split(",")])

    # open file handle to redirect output
    redr_file = open(CREATED_FILES[0], "w+")

    # check if installed gobuster is older and has only mode 'dir'
    is_old_gobuster = check_is_old_gobuster()

    for (ip, host, port, protocol) in TARGETS:
        # for every new IP create a new webserver_map entry and print a seperator
        if ip not in webserver_map:
            webserver_map[ip] = {}
            LOGGER.info("Initiating scan for %s", ip)
            if VERBOSE:
                util.printit("*" * 30)
                redr_file.write("*" * 30 + "\n")

                util.printit("+ " + ip + " " + "*" * (27 - len(ip)))
                redr_file.write("+ " + ip + " " + "*" * (27 - len(ip)) + "\n")

                util.printit("*" * 30)
                redr_file.write("*" * 30 + "\n")

        if port not in webserver_map[ip]:
            webserver_map[ip][port] = {}
        if host in webserver_map[ip][port]:
            continue

        # omit port in url if possible
        if (protocol == "http" and port == "80") or (protocol == "https" and port == "443"):
            url = protocol + "://" + host
        else:
            url = protocol + "://" + host + ":" + port

        # run gobuster on target URL and save the results
        host_web_map = run_gobuster(url, redr_file, is_old_gobuster)
        webserver_map[ip][port][host] = host_web_map

    # close redirect file
    redr_file.close()

    LOGGER.info("Finished gobuster scan")
    results.append((ResultType.WEBSERVER_MAP, webserver_map))


def check_is_old_gobuster():
    """
    Check if the installed gobuster is older and has mode "dir", since this leads
    to a slightly different call syntax.
    """

    # check how to use gobuster information for version estimation
    try:
        check_out = subprocess.check_output(["gobuster", "dir"], stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        check_out = e.output
    check_out = check_out.decode()
    if ("2 errors occurred" in check_out and "WordList (-w): Must be specified" in check_out and "Url/Domain (-u): Must be specified" in check_out):
        return True
    return False


def run_gobuster(url, redr_file, is_old_gobuster):
    """
    Run gobuster on the target URL and process its results.

    :param url: the URL to run gobuster on
    :param redr_file: the file to redirect the output of gobuster to
    :return: a webserver_map that contains the formated results of the gobuster scan
    """
    depth = int(CONFIG["depth"])
    dirs = ["/"]  # keeps track of all dirs to brute force

    webserver_map = {}
    start_host = datetime.datetime.now()

    # run gobuster once for every discovered directory
    for dir_ in dirs:
        # stop if the maximum depth was reached ...
        if dir_.count("/") > depth:
            break
        # ... or too much time was spent bruteforcing this host
        elif ((datetime.datetime.now() - start_host).total_seconds() >
              int(CONFIG["per_host_timeout"])):
            redr_file.write("\nWARNING: HOST SEARCH TIMEOUT ('%s', >%ss)\n" %
                            (url, CONFIG["per_host_timeout"]))
            if VERBOSE:
                util.printit("\nWARNING: HOST SEARCH TIMEOUT ('%s', >%ss)\n" %
                             (url, CONFIG["per_host_timeout"]), color=util.RED)
            break

        # setup gobuster parameters
        cur_url = url + dir_
        gobuster_call = ["gobuster", "-t", CONFIG["threads"], "-w", CONFIG["wordlist"],
                         "-u", cur_url, "-x", CONFIG["extensions"], "-k"]
        if not is_old_gobuster:
            gobuster_call.insert(1, "dir")

        findings = []
        printed_starting, printing_results = False, False
        prev_line_is_progress = False
        start_dir = datetime.datetime.now()

        # start gobuster and in parallel handle the printing,
        # check for timeouts and append the results
        with subprocess.Popen(gobuster_call, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              bufsize=1, universal_newlines=True) as proc:

            for line in proc.stdout:
                # check for timeouts on every new printed line
                if ((datetime.datetime.now() - start_dir).total_seconds() >
                        int(CONFIG["per_directory_timeout"])):
                    redr_file.write("\nWARNING: DIRECTORY SEARCH TIMEOUT ('%s', >%ss)\n" %
                                    (dir_, CONFIG["per_directory_timeout"]))
                    if VERBOSE:
                        util.printit("\nWARNING: DIRECTORY SEARCH TIMEOUT ('%s', >%ss)\n" %
                                     (dir_, CONFIG["per_directory_timeout"]), color=util.RED)
                    proc.kill()
                    break
                elif ((datetime.datetime.now() - start_host).total_seconds() >
                      int(CONFIG["per_host_timeout"])):
                    proc.kill()
                    break

                # handle some weird gobuster printing behavior
                if line.startswith("\x1b[2K"):
                    line = line[len("\x1b[2K"):]
                if printing_results and line.strip() == "":
                    continue

                # if the previous line was a progress indicator, remove it to make
                # it possible to orderly print in verbose mode
                if VERBOSE:
                    if prev_line_is_progress:
                        util.acquire_print()
                        util.clear_previous_line()
                        util.release_print()
                        delete_last_line(redr_file)

                    prev_line_is_progress = line.startswith("Progress: ")
                    util.printit(line, end="")
                redr_file.write(line)

                # skip errors
                if line.startswith("[ERROR]"):
                    continue

                # skip the front matter of gobuster when handling results
                if "Starting gobuster" in line:
                    printed_starting = True
                elif "================" in line and printed_starting and (not printing_results):
                    printing_results = True
                elif "================" in line and printing_results:
                    printing_results = False
                elif printing_results:
                    line = line.strip()
                    if line:
                        entry = line[:line.find("(")].strip()
                        code_start = line.find("Status: ") + len("Status: ")
                        code = line[code_start:code_start+3]
                        findings.append((entry, code))

        # extract new dirs and process findings
        new_dirs = process_gobuster_findings(url, dir_, findings, webserver_map)
        dirs += new_dirs

        # print empty line after every gobuster call
        util.printit("")
        redr_file.write("\n")

    return webserver_map


def process_gobuster_findings(base_url, cur_dir, findings, webserver_map):
    """
    Process findings to retrieve new directories and handle redirects.
    A finding is a tuple (path, HTTP code).

    :param orig_url: the URL that gobuster was run on first
    :param cur_dir: the current directory that was just bruteforced
    :param findings: the list of findings
    :param webserver_map: the current webserver map
    :return: the new relative directories to bruteforce
    """

    def circumvent_redirect():
        nonlocal resp, path, code_str

        resp = requests.get(redirect_to, allow_redirects=False)
        path = path + "/"
        code_str = str(resp.status_code)

    def store_redirect():
        nonlocal code_str, path, redirect_to

        if code_str not in webserver_map:
            webserver_map[code_str] = {}
        webserver_map[code_str][path] = {"misc_info": "redirect to %s" % redirect_to}


    new_dirs = []
    for finding in findings:
        # Get HTTP code of the response of the finding
        try:
            code_str = finding[1]
            code = int(code_str)
        except:
            continue

        # build absolute path from relative directory of finding
        if finding[0].startswith("/"):
            path = cur_dir + finding[0][1:]
        else:
            path = cur_dir + finding[0]

        # get location of redirect
        if code == 301 or code == 302:
            resp = requests.get(base_url + path, allow_redirects=False)
            redirect_to = resp.headers["Location"]
            # handle redirect to a complete URL
            if redirect_to.startswith("http"):
                # if the redirect just adds '/' to the directory, do not store the redirect ...
                if redirect_to == base_url + path + "/":
                    circumvent_redirect()
                # ... otherwise store the redirect in the webserver_map
                else:
                    store_redirect()
                    continue
            # handle redirect to another path
            else:
                # try to fix / understand different representations of the redirect path
                if (redirect_to == path + "/") or ("/" + redirect_to == path + "/"):
                    circumvent_redirect()
                # if can't handle, just store the redirect
                else:
                    store_redirect()
                    continue

        # add new path to webserver_map
        if code_str not in webserver_map:
            webserver_map[code_str] = {}
        webserver_map[code_str][path] = {}

        # add new directory to be bruteforced
        if finding[0][finding[0].find("/")+1:] not in EXCLUDE_DIRS:
            if path.endswith("/"):
                new_dirs.append(path)
            elif CONFIG["allow_file_depth_search"].lower() == "true":
                new_dirs.append(path + "/")

    return new_dirs


def set_targets():
    """
    Determine the targets to run gobuster against. Targets are determined
    by looking at port numbers, service infos and service names.
    """

    global TARGETS

    def add_targets(ip, port, protocol):
        """
        Add as targets this (ip, port, protocol) combination together with every
        available domain name for that IP to deal with virtual hosts.
        """
        nonlocal hosts

        for host in hosts:
            TARGETS.append((ip, host, port, protocol))


    for ip, host_info in INTERMEDIATE_RESULTS[ResultType.SCAN].items():
        hosts = get_hosts(ip)
        for portid, portinfos in host_info["tcp"].items():
            for portinfo in portinfos:
                if portid == "80":
                    add_targets(ip, portid, "http")
                elif portid == "443":
                    add_targets(ip, portid, "https")
                elif "service" in portinfo:
                    if "http" in portinfo["service"].lower():
                        add_targets(ip, portid, "http")
                    elif "https" in portinfo["service"].lower():
                        add_targets(ip, portid, "https")
                elif "name" in portinfo:
                    if "http" in portinfo["name"].lower():
                        add_targets(ip, portid, "http")
                    elif "https" in portinfo["name"].lower():
                        add_targets(ip, portid, "https")


def get_hosts(ip):
    """
    Return a list containing either only the given IP or a list of all
    available domain names that are bound to this IP. Names are first
    looked up in the local /etc/hosts file and then by actual reverse DNS.
    """

    hosts = []
    if CONFIG["do_reverse_dns"].lower() == "true":
        try:
            with open("/etc/hosts") as f:
                entries = f.read().split("\n")
                for entry in entries:
                    entry = entry.strip()
                    if entry.startswith(ip + " "):
                        hosts.append(entry[entry.rfind(" ")+1:])
        except FileNotFoundError:
            pass

        if not hosts:
            try:
                hosts.append(socket.gethostbyaddr(ip)[0])
            except socket.herror:
                hosts.append(ip)

    else:
        hosts = [ip]

    return hosts


def delete_last_line(file):
    """
    Delete the last line of the file handled by the "file" parameter
    Adapted from https://stackoverflow.com/a/10289740
    """

    # Move the pointer (similar to a cursor in a text editor) to the end of the file
    file.seek(0, os.SEEK_END)

    # This code means the following code skips the very last character in the file -
    # i.e. in the case the last line is null we delete the last line
    # and the penultimate one
    pos = file.tell() - 1

    # Read each character in the file one at a time from the penultimate
    # character going backwards, searching for a newline character
    # If we find a new line, exit the search
    while pos > 0 and file.read(1) != "\n":
        pos -= 1
        file.seek(pos, os.SEEK_SET)
    pos += 1

    # So long as we're not at the start of the file, delete all the characters ahead
    # of this position
    if pos > 0:
        file.seek(pos, os.SEEK_SET)
        file.truncate()
