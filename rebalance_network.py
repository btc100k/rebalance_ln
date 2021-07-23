import json
import shlex
import subprocess

DEBUG = False
MINIMUM_NODE_DISTANCE = 7
MAX_NODE_DISTANCE = 4
MIN_CHANNEL_CAPACITY = 500000
MINIMUM_CHANNEL_COUNT = 5
MINIMUM_BTC_COUNT = 0.10


class RemoteChannel:
    def __init__(self, record):
        # (u'stratum+tcp://ca.stratum.slushpool.com:3333', 3, u'bluegrass.')
        self.channel_id = record["channel_id"]
        self.node1_pub = record["node1_pub"]
        self.node2_pub = record["node2_pub"]
        self.capacity = int(record["capacity"])
        self.channel_point = record["chan_point"]


class RemoteNode:
    def __init__(self, record):
        node_record = record["node"]
        self.alias = node_record["alias"]
        self.pub_key = node_record["pub_key"]
        self.num_channels = int(record["num_channels"])
        self.total_capacity = int(record["total_capacity"])

        self.full_address = self.pub_key
        address_array = node_record["addresses"]
        for one_address in address_array:
            # favor the TOR address,
            if "onion" in one_address["addr"]:
                self.full_address = self.pub_key + "@" + one_address["addr"]
                break
            else:
                self.full_address = self.pub_key + "@" + one_address["addr"]
        self.remote_channels = []


class Channel:
    def __init__(self, record):
        # (u'stratum+tcp://ca.stratum.slushpool.com:3333', 3, u'bluegrass.')
        self.channel_id = record["chan_id"]
        self.remote_pubkey = record["remote_pubkey"]
        self.remote_balance = int(record["remote_balance"])
        self.local_balance = int(record["local_balance"])
        self.total_satoshis_sent = int(record["total_satoshis_sent"])
        self.total_satoshis_received = int(record["total_satoshis_received"])
        self.private = bool(record["private"])
        self.active = bool(record["active"])
        self.channel_point = record["channel_point"]

    def balance_ratio(self):
        if self.local_balance == 0:
            return 1.0
        if self.remote_balance == 0:
            return 0.0

        # this gets me a number between 0 & 1
        total = self.remote_balance + self.local_balance
        return float(self.remote_balance) / float(total)

    def balance_score(self):
        if self.local_balance == 0:
            return 0.0
        if self.remote_balance == 0:
            return 1000.0
        return float(self.remote_balance) / float(self.local_balance)

    def out_of_balance(self):
        balance_score = self.balance_ratio()
        if balance_score > 0.75 or balance_score < 0.25:
            return True
        return False


class Commandline:
    def __init__(self, command):
        self.command_args = shlex.split(command)
        self.output = ""
        self.error = ""
        self.exit_code = 0

    def run(self):
        try:
            stdout = subprocess.check_output(self.command_args)
            stderr = None
        except subprocess.CalledProcessError as err:
            stdout = None
            stderr = err.output
            self.exit_code = err.returncode

        if stdout is None:
            self.output = ""
        else:
            self.output = stdout.decode("utf-8")
        if stderr is None:
            self.error = ""
        else:
            self.error = stderr.decode("utf-8")


def get_lncli():
    which_lncli = Commandline("which lncli")
    which_lncli.run()
    lncli_alias = "lncli"
    if len(which_lncli.error) > 0:
        print("Failed to determine where lncli is located", which_lncli.error)
        exit(1)
    elif len(which_lncli.output) > 0:
        # this should work on non-umbrel nodes (but I haven't tested)
        lncli_alias = "lncli"
    else:
        # docker is for running on the umbrel
        lncli_alias = "docker exec -it lnd lncli"

    if DEBUG:
        print("Using {lncli}".format(lncli=lncli_alias))
    return lncli_alias


def get_channels():
    listchannels = '{lncli} listchannels --active_only --public_only'.format(lncli=lncli_cmd)
    if DEBUG:
        print(listchannels)
        print("-" * 15)
    data = {}
    list_channels = Commandline(listchannels)
    list_channels.run()
    if len(list_channels.error) > 0:
        print("Failed to get channels", list_channels.error)
        exit(1)
    elif len(list_channels.output) > 0:
        data = json.loads(list_channels.output)
    else:
        print("No channels found")
        exit(2)

    result_array = []
    the_channels = data["channels"]
    for channel_record in the_channels:
        one = Channel(channel_record)
        result_array.append(one)

    return result_array


def get_remote_node(pubkey):
    getnodeinfo = '{lncli} getnodeinfo --pub_key {pubkey} --include_channels true'.format(
        lncli=lncli_cmd, pubkey=pubkey)
    if DEBUG:
        print(getnodeinfo)
        print("-" * 15)
    info_command = Commandline(getnodeinfo)
    info_command.run()
    if len(info_command.error) > 0:
        print("Node Info Failed - Skipping {pubkey}.".format(pubkey=pubkey))
        if DEBUG:
            print(info_command.error)
    elif len(info_command.output) > 0:
        data = json.loads(info_command.output)
        the_channels = data["channels"]
        response_node = RemoteNode(data)

        for channel_record in the_channels:
            one = RemoteChannel(channel_record)
            response_node.remote_channels.append(one)
        return response_node
    else:
        print("No channels found - Skipping {pubkey}.".format(pubkey=pubkey))

    return None


def get_route_length(pubkey):
    get_route = '{lncli} queryroutes --dest {pubkey} --amt 15000 --fee_limit 150'.format(
        lncli=lncli_cmd, pubkey=pubkey)
    if DEBUG:
        print(get_route)
        print("-" * 15)
    route_command = Commandline(get_route)
    route_command.run()
    if len(route_command.error) > 0:
        if DEBUG:
            print(get_route)
            print(route_command.error)
        # print("-" * 15)
        if "unable to find a path to destination" in route_command.error:
            return -1
        else:
            print("Route Failed despite offering 1% fee - {pubkey}.".format(pubkey=pubkey))
            print(route_command.error)
            print("-" * 33)
    elif len(route_command.output) > 0:
        data = json.loads(route_command.output)
        routes = data["routes"]
        r_len = 100
        for route in routes:
            hops = route["hops"]
            if len(hops) < r_len:
                r_len = len(hops)
        return r_len
    else:
        if DEBUG:
            print("No route found - Skipping {pubkey}.".format(pubkey=pubkey))
    return 0


print("We're going to look at all the channels of the nodes to which you have outbound channels")
print("   we're looking for nodes which are distant to you.")
print("If you had a direct connection to a sufficiently distant node, ")
print("   you'll cut the path in half to any node on the route.")
print("+" * 20)

minimum_distance = input('What is the shortest route to consider?: (Default: {default}) '.format(
    default=MINIMUM_NODE_DISTANCE))
if len(minimum_distance) == 0 or int(minimum_distance) <= 0:
    minimum_distance = MINIMUM_NODE_DISTANCE
else:
    minimum_distance = int(minimum_distance)

minimum_capacity = input('Minimum channel capacity to consider nodes?: (Default: {default}) '.format(
    default=MIN_CHANNEL_CAPACITY))
if len(minimum_capacity) == 0 or int(minimum_capacity) <= 0:
    minimum_capacity = MIN_CHANNEL_CAPACITY
else:
    minimum_capacity = int(minimum_capacity)

lncli_cmd = get_lncli()
all_channels = get_channels()
print("")
print("Collecting information on your channels:", len(all_channels))
print("+" * 20)

pubkey_hop_map = {}
next_level_nodes = []
for one_channel in all_channels:
    if one_channel.remote_pubkey not in next_level_nodes:
        next_level_nodes.append(one_channel.remote_pubkey)

for distance in range(1, MAX_NODE_DISTANCE):
    all_pubkeys = next_level_nodes
    next_level_nodes = []
    print("Collecting channels for level", (distance + 1), "nodes:", len(all_pubkeys))
    print("+" * 20)
    for one_pubkey in all_pubkeys:
        if DEBUG:
            print("---", one_pubkey)
        remote_node = None
        if one_pubkey not in pubkey_hop_map:
            remote_node = get_remote_node(one_pubkey)
        if remote_node is not None and remote_node.pub_key not in pubkey_hop_map:
            # This node has not been seen previously
            # so it is probably worth digging in here
            # if it is far enough away, we can choose this node as a candidate
            # if it is not far enough away, we dive deeper to this node's peers
            pubkey_hop_map[remote_node.pub_key] = distance
            for one_remote_channel in remote_node.remote_channels:
                # If this channel has enough capacity
                if one_remote_channel.capacity >= minimum_capacity:
                    # If this node isn't already in our to-do list
                    if one_remote_channel.node2_pub not in next_level_nodes:
                        # if this node wasn't visited on a previous level
                        if one_remote_channel.node2_pub not in pubkey_hop_map:
                            next_level_nodes.append(one_remote_channel.node2_pub)
                elif DEBUG:
                    print("-- This node has a channel too small to follow:", remote_node.pub_key)
                    print("   Destination node:", one_remote_channel.node2_pub)
                    print("   Capacity:", one_remote_channel.capacity)

            if distance >= 2:
                total_btc = remote_node.total_capacity / 100000000
                if remote_node.num_channels > MINIMUM_CHANNEL_COUNT and total_btc >= MINIMUM_BTC_COUNT:
                    route_length = get_route_length(remote_node.pub_key)
                    if route_length >= minimum_distance:
                        print("   Here is a good candidate node:", remote_node.pub_key)
                        print("   Alias:", remote_node.alias)
                        print("   Link: https://1ml.com/node/{pubkey}".format(pubkey=remote_node.pub_key))
                        print("   Addr:", remote_node.full_address)
                        print("   Channels:", remote_node.num_channels)
                        total_btc = remote_node.total_capacity / 100000000
                        print("   Total Capacity:", "{:0.2f} BTC".format(float(total_btc)))
                        print("   Number of hops:", route_length)
                        print("-" * 33)
                    elif route_length == -1:
                        print("     Failed to create route to", remote_node.pub_key)
                        print("         This node could be offline.")
                        print("         or there might be no routes available.")
                        print("     Alias:", remote_node.alias)
                        print("     Link: https://1ml.com/node/{pubkey}".format(pubkey=remote_node.pub_key))
                        print("     Addr:", remote_node.full_address)
                        print("     Channels:", remote_node.num_channels)
                        print("     Total Capacity:", "{:0.2f} BTC".format(float(total_btc)))
                        print("-" * 33)
                else:
                    # this node has too few channels, or too little capacity
                    pass

            elif DEBUG:
                print("-- This node is too close:", remote_node.pub_key)
                print("   Distance:", distance)
        else:
            # we have already seen this node. Nothing to do here.
            if DEBUG:
                print("--- None response, or already seen pub_key", remote_node)
            pass
