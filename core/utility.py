import ipaddress
import sys
import datetime


# TODO: How to handle broadcast and network identifier addresses. Decide to include or not and fix.

def parse_wildcard_ipv4(network: str):
    def get_all_hosts(splits):
        if splits:
            if len(splits) == 1:
                return [str(i) for i in splits[0]]
            else:
                all_concat = []
                all_after = get_all_hosts(splits[1:])
                for i in splits[0]:
                    for j in all_after:
                        all_concat.append("%d.%s" % (i, j))
                return all_concat
        else:
            return []

    cidr = None
    if "/" in network:
        cidr = "".join(network[network.rfind("/")+1:])
        network = network[:network.rfind("/")]
    split_ip = network.split(".")

    for i, num in enumerate(split_ip):
        # only digit no wildcard
        try:
            num_int = int(num)
            if num_int in range(0, 256):
                split_ip[i] = [num_int]
            else:
                raise ValueError("A textual IP address does not contain numbers above 255")
        except ValueError:
            if "*" in num:
                if len(num) > 3:
                    raise ValueError("A textual IP address does not contain four-digit numbers")
                if num.count("*") > 1:
                    raise ValueError("You cannot have two wildcard symbols within one IP number")

                if num[0] == "*":
                    if len(num) == 3:
                        for j in range(10):
                            split_ip[i] += j * 100 + int(num[1:2])
                    elif len(num) == 2:
                        for j in range(10):
                            split_ip[i] += j * 10 + int(num[1])
                    else:
                        split_ip[i] = list(range(0, 256))
                elif num[1] == "*":
                    if len(num) == 3:
                        for j in range(10):
                            split_ip[i] += int(num[0]) * 100 + j * 10 + int(num[2])
                    elif len(num) == 2:
                        for j in range(10):
                            split_ip[i] += int(num[0]) * 10 + j
                elif num[2] == "*":
                    if len(num) == 3:
                        for j in range(10):
                            split_ip[i] += int(num[0]) * 100 + int(num[2]) * 10 + j 
            elif "-" in num:
                l, r = num.split("-")
                split_ip[i] = range(int(l), int(r)+1)

    if not cidr:
        return get_all_hosts(split_ip)
    else:
        all_hosts_no_cidr = get_all_hosts(split_ip) 
        all_hosts = []

        for host in all_hosts_no_cidr:
            all_hosts += parse_cidr_ipv4(host + "/" + cidr)

        return all_hosts

def is_cidr_ipv4(network: str):
    try:
        ipaddress.ip_network(network)
        return True
    except ValueError:
        return False

def parse_cidr_ipv4(network: str):
    if "/" in network:
        return list(str(ip) for ip in ipaddress.ip_network(network).hosts())
    else:
        return network

def is_valid_net_addr(network):
    if not is_cidr_ipv4(network):
        if (not "-" in network) and (not "*" in network):
            return False
    return True

def extend_network_to_hosts(network):
    if "*" in network or "-" in network:
        return parse_wildcard_ipv4(network)
    else:
        return parse_cidr_ipv4(network)

def ip_str_to_number(ip):
    return int.from_bytes([int(ip) for ip in ip.split(".")], "big")

def print_exception_and_continue(e):
    print("Original exception is: ", file=sys.stderr)
    print(e, file=sys.stderr)
    print("===========================================================", file=sys.stderr)
    print("Continuing with scan ...", file=sys.stderr)


def get_current_timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")