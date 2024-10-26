MAX_BLOCKS = 10000
DEV_TIMEOUT = 60

from jnpr.junos import Device
from collections import defaultdict, Counter
import argparse
import ipaddress
from time import time

# variable for tracing execution times of various blocks
global trace_time_points
trace_time_points = []


def parse_args():
    """argument parsing"""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--nat-pool", dest="nat_pool")
    parser.add_argument("--port-threshold", type=int)
    parser.add_argument("--trace")
    parser.add_argument("--max-blocks", type=int)
    parser.add_argument("--node")
    return parser.parse_args()


def get_nat_ip_data(dev, nat_pool, node):
    """retrieve data
    view approach gives the same performance, but is way slower when pre-processed
    the scalable but slower and less accurate way may be to retrieve NAT pool and walk one after another pool NAT
    """

    # chassis cluster specific to avoid double counting
    if node:
        rpc_output = dev.rpc.get_src_nat_port_block(
            dev_timeout=DEV_TIMEOUT, normalize=True, pool=nat_pool, node=node
        )
    # standalone / MNHA
    else:
        rpc_output = dev.rpc.get_src_nat_port_block(
            dev_timeout=DEV_TIMEOUT,
            normalize=True,
            pool=nat_pool,
        )

    record_time_trace("get_nat_ip_data-rpc")

    # internal host IPs
    internal_ips = [item.text for item in rpc_output.findall(".//blk-internal-ip")]
    # translated IPs
    reflexive_ips = [item.text for item in rpc_output.findall(".//blk-reflexive-ip")]
    # ports used in blocks
    blocks_ports_used = [item.text for item in rpc_output.findall(".//blk-ports-used")]

    record_time_trace("get_nat_ip_data-lists_load")

    return internal_ips, reflexive_ips, blocks_ports_used


def preprocess_ips(internal_ips, reflexive_ips, blocks_ports_used):
    """data pre-processing before analyze and print"""
    # defaultdict used to count occurences of the same value in list
    reflexive_ip_count = defaultdict(int)
    reflexive_ip_blocks_count = defaultdict(int)
    internal_ip_ports_used = defaultdict(int)
    internal_ip_blocks_used = defaultdict(int)
    # elements in set are unique
    unique_internal_ips = set()

    for internal_ip, reflexive_ip, block_ports_used in zip(
        internal_ips, reflexive_ips, blocks_ports_used
    ):
        if internal_ip not in unique_internal_ips:
            # occurences of NAT IP, assumes address-persistent or pooling paired
            reflexive_ip_count[reflexive_ip] += 1
            unique_internal_ips.add(internal_ip)
        # how many blocks are used per specific NAT IP
        reflexive_ip_blocks_count[reflexive_ip] += 1
        # ports in use for specific internal host IP
        internal_ip_ports_used[internal_ip] += int(block_ports_used)
        # blocks in use for specific internal host
        internal_ip_blocks_used[internal_ip] += 1

    return (
        reflexive_ip_count,
        reflexive_ip_blocks_count,
        unique_internal_ips,
        internal_ip_ports_used,
        internal_ip_blocks_used,
    )


def analyze_and_print(
    port_threshold,
    reflexive_ip_count,
    reflexive_ip_blocks_count,
    unique_internal_ips,
    internal_ip_ports_used,
    internal_ip_blocks_used,
    total_blocks,
    block_size,
    max_blocks,
    cluster,
    aa_cluster,
):
    record_time_trace("analyze_and_print start")

    print_header("NAT-IP : #int-hosts/alloc blk")
    # prints number of internal hosts and allocated blocks per NAT-IP
    for reflexive_ip, count in reflexive_ip_count.items():
        print(f"{reflexive_ip:<16}: {count}/{reflexive_ip_blocks_count[reflexive_ip]}")

    record_time_trace("analyze_and_print 1")

    # prints internal host max/min/avg count per NAT-IP
    print_header("Int-hosts per NAT-IP stats")
    print(f"max             : {max(reflexive_ip_count.values())}")
    print(f"min             : {min(reflexive_ip_count.values())}")
    print(
        f"avg             : {round(sum(reflexive_ip_count.values()) / len(reflexive_ip_count),2):.2f}"
    )

    # prints allocated blocks max/main/avg per NAT-IP
    print_header("Blk per NAT-IP")
    print(f"capacity        : { 64512 // block_size }")
    if cluster:
        if aa_cluster:
            # A/A cluster divides NAT pool resources between nodes
            print(f"capacity(node)  : { ( 64512 // block_size ) // 2 }")
        else:
            # for explicit A/P cluster mode
            print(f"capacity(node)  : { ( 64512 // block_size )}")
    print(f"max used        : {max(reflexive_ip_blocks_count.values())}")
    print(f"min used        : {min(reflexive_ip_blocks_count.values())}")
    print(
        f"avg used        : {round(sum(reflexive_ip_blocks_count.values()) / len(reflexive_ip_blocks_count),2):.2f}"
    )

    # prints PBA parameters based on configured settings
    allocated_blocks = sum(reflexive_ip_blocks_count.values())
    print_header("PBA pool stats")
    print(f"blk size        : {block_size}")
    print(f"maximum blk     : {max_blocks}")
    print(f"total blk       : {total_blocks}")
    if cluster:
        if aa_cluster:
            # A/A cluster divides NAT pool resources between nodes
            print(f"total blk(node) : {total_blocks // 2}")
        else:
            # for explicit A/P cluster mode
            print(f"total blk(node) : {total_blocks}")
    print(f"allocated blk   : {allocated_blocks}")
    if aa_cluster:
        print(
            f"utilization     : {round((allocated_blocks / ( total_blocks // 2 ) ) * 100,1):.1f}%"
        )
    else:
        print(
            f"utilization     : {round((allocated_blocks / ( total_blocks )) * 100,1):.1f}%"
        )

    #  prints internal host statistics
    print_header("Int-host stats")
    print(f"unique hosts    : {len(unique_internal_ips)}")
    print(
        f"avg blk         : {round(allocated_blocks / len(unique_internal_ips),2):.2f}"
    )
    print(f"total sess      : {sum(internal_ip_ports_used.values())}")
    print(f"max sess        : {max(internal_ip_ports_used.values())}")
    print(
        f"avg sess        : {round(sum(internal_ip_ports_used.values()) / len(unique_internal_ips),1):.1f}"
    )

    # calculates number of used blocks per internal host
    host_num_blocks = Counter(internal_ips)

    # calculates number of internal hosts per specific allocated blocks cohort
    block_count_hosts = Counter(host_num_blocks.values())

    record_time_trace("analyze_and_print 2")

    print_header("Stats per alloc blk cohort ")

    for blocks, hosts in sorted(block_count_hosts.items()):
        # prints how many hosts have specific number of allocated blocks
        print(f"blk/hosts       : {blocks}/{hosts}")
    print("-" * 16)

    record_time_trace("analyze_and_print 3")

    for blocks, hosts in sorted(block_count_hosts.items()):
        # prints how many hosts have specific number of allocated blocks in percentage
        print(
            f"blk/percent     : {blocks}/{(hosts / len(unique_internal_ips))*100:.1f}%"
        )
    print("-" * 16)

    record_time_trace("analyze_and_print 4")

    block_size_max_ports = {}
    block_size_avg_ports = {}
    for blocks, hosts in sorted(block_count_hosts.items()):
        record_time_trace(f"analyze_and_print 5 blocks:{blocks}")
        # builds a list of hosts with specific number of blocks
        hosts_with_block_size = [
            host
            for host, host_blocks in internal_ip_blocks_used.items()
            if host_blocks == blocks
        ]

        record_time_trace(f"analyze_and_print 6 blocks:{blocks}")

        # builds list of used ports for specific number of blocks
        ports_for_block_size = [
            host_ports
            for host, host_ports in internal_ip_ports_used.items()
            if host in hosts_with_block_size
        ]

        record_time_trace(f"analyze_and_print 7 blocks:{blocks}")

        # maximum ports for particular block allocation cohort
        block_size_max_ports[blocks] = max(ports_for_block_size)
        # avg ports for particular block allocation cohort
        block_size_avg_ports[blocks] = round(
            sum(ports_for_block_size) / len(hosts_with_block_size)
        )

    record_time_trace("analyze_and_print 8")

    for blocks, max_ports_for_block_size in block_size_max_ports.items():
        # prints maximum sessions per block allocation cohort
        print(f"blk/max sess    : {blocks}/{max_ports_for_block_size}")
    print("-" * 16)

    record_time_trace("analyze_and_print 9")

    for blocks, avg_ports_for_block_size in block_size_avg_ports.items():
        # prints avg sessions per block allocation cohort in percent
        print(f"blk/avg sess    : {blocks}/{avg_ports_for_block_size}")

    # if enabled print hosts crossing certain port allocation threshold
    if port_threshold:
        print_header("Hosts >= port-threshold")
        if port_threshold > 0:
            for host, host_ports in sorted(
                internal_ip_ports_used.items(),
                key=lambda item: ipaddress.ip_address(item[0]),
            ):
                if host_ports >= port_threshold:
                    print(f"{host:<16}:{host_ports}")
        else:
            print("port-threshold must be > 0")

    record_time_trace("analyze_and_print 10")


def print_header(message: str):
    print("-" * 30)
    print(f"{message}")
    print("-" * 15 + ">")


def record_time_trace(tracepoint: str, print_records=False):
    """record tracepoints when diagnosting execution time"""
    if tracepoint:
        trace_time_points.append([time(), tracepoint])

    if print_records:
        print_header("Exec time trace")
        for i in range(len(trace_time_points)):
            if i > 0:
                print(
                    f"{trace_time_points[i][0] - trace_time_points[i - 1][0]:<7.3f} {trace_time_points[i][1]}"
                )


def nat_pools_info(dev):
    """retrieve NAT pool information"""
    rpc_output = dev.rpc.retrieve_source_nat_pool_information(
        dev_timeout=DEV_TIMEOUT, normalize=True, all=True
    )
    pba_pools = {}

    for nat_pool_record in rpc_output.findall(".//source-nat-pool-info-entry"):
        # check for PBA enabled
        if nat_pool_record.findall(".//source-pool-blk-total"):
            pba_pool = nat_pool_record.findall(".//pool-name")[0].text
            pba_pools[pba_pool] = {}
            pba_pools[pba_pool]["block_size"] = int(
                nat_pool_record.findall(".//source-pool-blk-size")[0].text
            )
            pba_pools[pba_pool]["max_blocks"] = int(
                nat_pool_record.findall(".//source-pool-blk-max-per-host")[0].text
            )
            pba_pools[pba_pool]["blocks_total"] = int(
                nat_pool_record.findall(".//source-pool-blk-total")[0].text
            )
            pba_pools[pba_pool]["blocks_used"] = int(
                nat_pool_record.findall(".//source-pool-blk-used")[0].text
            )

    return pba_pools


def is_cluster(dev):
    """checks if the device is a chassis cluster"""
    rpc_output = dev.rpc.get_chassis_cluster_status()
    for node in rpc_output.findall(".//cluster-id"):
        return True
    return False


def is_aa_cluster(dev):
    """checks if the device is A/A operational mode chassis cluster
    A/P is explicit set chassis cluster redundancy-mode active-backup"""
    rpc_output = dev.rpc.get_chassis_cluster_detail_information()
    if rpc_output.findall(".//operational")[0].text == "active-active":
        return True
    else:
        return False


with Device() as dev:
    args = parse_args()

    if args.trace in ["time"]:
        record_time_trace("start")
        trace_time = True
    else:
        trace_time = False

    nat_pool = args.nat_pool
    port_threshold = args.port_threshold
    if args.max_blocks:
        MAX_BLOCKS = args.max_blocks

    node = args.node
    # checks for chassis cluster
    cluster = is_cluster(dev)
    aa_cluster = False
    if cluster:
        aa_cluster = is_aa_cluster(dev)

    if cluster and node not in ["0", "1"]:
        print("Specify chassis cluster node [0|1]")
    else:
        # retrieve NAT pool info
        pba_pools = nat_pools_info(dev)

        record_time_trace("nat_pools_info")

        # case with only one NAT pool
        if len(pba_pools) == 1 and not nat_pool:
            nat_pool = list(pba_pools.keys())[0]

        # more NAT pools and none specified
        if len(pba_pools) > 1 and not nat_pool:
            print("More than one PBA enabled pool found:")
            for pba_pool in pba_pools:
                print(pba_pool)
            print("Use nat-pool [pool-name] argument")

        # no NAT pool case
        elif len(pba_pools) == 0:
            print("No PBA enabled pool found")

        # wrong NAT pool name entered
        elif not nat_pool in pba_pools:
            print(f"No such PBA NAT pool: {nat_pool}, available PBA pools:")
            for pba_pool in pba_pools:
                print(pba_pool)

        # no NAT pool selection error
        else:
            blocks_used = pba_pools[nat_pool]["blocks_used"]
            if blocks_used > MAX_BLOCKS:
                print(
                    f"Used blocks {blocks_used} is above limit of {MAX_BLOCKS}, tune MAX_BLOCKS according to device resources"
                )

            # within limits, proceed
            else:
                # retrieve NAT pool data
                internal_ips, reflexive_ips, blocks_ports_used = get_nat_ip_data(
                    dev, nat_pool, node
                )

                record_time_trace("get_nat_ip_data")

                # preprocess
                (
                    reflexive_ip_count,
                    reflexive_ip_blocks_count,
                    unique_internal_ips,
                    internal_ip_ports_used,
                    internal_ip_blocks_used,
                ) = preprocess_ips(internal_ips, reflexive_ips, blocks_ports_used)

                record_time_trace("preprocess_ips")

                # analyze and print
                if reflexive_ip_count:
                    analyze_and_print(
                        port_threshold,
                        reflexive_ip_count,
                        reflexive_ip_blocks_count,
                        unique_internal_ips,
                        internal_ip_ports_used,
                        internal_ip_blocks_used,
                        int(pba_pools[nat_pool]["blocks_total"]),
                        int(pba_pools[nat_pool]["block_size"]),
                        int(pba_pools[nat_pool]["max_blocks"]),
                        cluster,
                        aa_cluster,
                    )

                    record_time_trace("analyze_and_print done")

                    if trace_time:
                        record_time_trace(None, print_records=True)

                    print("-" * 30)

                # PBA pool with no allocation
                else:
                    print(f"No PBA records in NAT pool: {nat_pool}")
