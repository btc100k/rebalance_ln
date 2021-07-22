import json
import shlex
import subprocess

DEBUG = False
DEFAULT_MAX_FEE = 50


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
            # print("+" * 20)
            # print("Command failure:", err.returncode)
            # print(err.output.decode("utf-8"))
            # print("+" * 20)
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


class PaymentInvoice:
    def __init__(self, record):
        self.r_hash = record["r_hash"]
        self.payment_request = record["payment_request"]
        self.add_index = record["add_index"]
        self.payment_addr = record["payment_addr"]


class PaymentRoute:
    def __init__(self, json_string):
        obj = json.loads(json_string)
        route = obj["route"]

        self.route_object = obj
        self.total_fees_msat = int(route["total_fees_msat"])
        self.total_amt_msat = int(route["total_amt_msat"])

    def add_invoice(self, invoice_obj, satoshi_total):
        route_object = self.route_object["route"]
        hops_object = route_object["hops"]
        # presuming this is an array
        hops_count = len(hops_object)
        one_hop = hops_object[(hops_count - 1)]
        total_msat = int(satoshi_total) * 1000
        one_hop["mpp_record"] = {"payment_addr": invoice_obj.payment_addr, "total_amt_msat": str(total_msat)}

        # now write it all back to the structure
        hops_object[(hops_count - 1)] = one_hop
        route_object["hops"] = hops_object
        self.route_object["route"] = route_object


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


def create_invoice(invoice_amount):
    addinvoice = '{lncli} addinvoice --expiry 360 --memo "Rebalance Ring" --amt {amount}'.format(
        lncli=lncli_cmd, amount=invoice_amount)
    if DEBUG:
        print(addinvoice)
        print("-" * 15)
    add_command = Commandline(addinvoice)
    add_command.run()
    the_invoice = ""
    if len(add_command.error) > 0:
        print("Failed to run invoice creation", add_command.error)
        exit(1)
    elif len(add_command.output) > 0:
        invoice_json = json.loads(add_command.output)
        if DEBUG:
            print(invoice_json)
            print("-" * 15)
        the_invoice = invoice_json

    if len(the_invoice) == 0:
        print("Failed to create an invoice")
        exit(2)
    return PaymentInvoice(the_invoice)


lncli_cmd = get_lncli()
all_channels = get_channels()

pub_keys = []
your_pub_key = ""

print("Enter all of the node ids in your ring.")
print("Start with the node where you have outbound liquidity.")
print("End with your node.")
print("---------------------------------------------------------")
print("Signal that you're done entering nodes with a blank line.")
print("---------------------------------------------------------")

user_nodes = []
nodes_map = {}
for x in range(500):
    input_channel_id = input('Enter a node id (remote pubkey): ')
    if len(input_channel_id) == 0:
        break
    else:
        nodes_map[input_channel_id] = 1
        user_nodes.append(input_channel_id)
        if len(nodes_map.keys()) != len(user_nodes):
            print("Duplicate nodes detected. Double check input.")
            exit(1)
print("---------------------------------------------------------")

satoshi_count = input('How many satoshis do you want to send? (Default: 5000) ')
print("---------------------------------------------------------")
if len(satoshi_count) <= 0:
    satoshi_count = 5000
else:
    satoshi_count = int(satoshi_count)

pubkey_map = {}
for one_channel in all_channels:
    pubkey_map[one_channel.remote_pubkey] = one_channel

first_node = user_nodes[0]
source_channel = pubkey_map[first_node]
chan_id_string = input('From what channel will the funds originate? '
                       '(Default: {expected}) '.format(
    expected=source_channel.channel_id))
print("---------------------------------------------------------")
if len(chan_id_string) == 0:
    chan_id_string = source_channel.channel_id

max_fee = DEFAULT_MAX_FEE
max_fee_string = input("What is the maximum fee you're willing to pay in satoishis?"
                       " (Default: {fee}) ".format(
    fee=max_fee))
print("---------------------------------------------------------")
if len(max_fee_string) == 0:
    max_fee = int(DEFAULT_MAX_FEE)
else:
    max_fee = int(max_fee_string)

if max_fee < 0:
    max_fee = 1

node_string = ",".join(user_nodes)
route_cmd = "{lncli} buildroute --amt {amount} --hops {nodes}" \
            " --outgoing_chan_id {channel_id}".format(
    lncli=lncli_cmd, amount=satoshi_count, nodes=node_string, channel_id=chan_id_string)
if DEBUG:
    print(route_cmd)
    print("-" * 15)
route_command = Commandline(route_cmd)
route_command.run()
if len(route_command.error) > 0:
    print("Failed to build the route", route_command.error)
    exit(1)
if DEBUG:
    print(route_command.output)
route_json = route_command.output
route_json = route_json.replace(" ", "")
route_json = route_json.replace("\n", "")
route_json = route_json.replace("\r", "")

the_route = PaymentRoute(route_json)
if the_route.total_fees_msat > int(max_fee * 1000):
    print("Fee required is higher than max", the_route.total_fees_msat, "vs", max_fee)
    exit(1)

invoice = create_invoice(satoshi_count)
if DEBUG:
    print("Invoice rhash", invoice.r_hash)
    print("-" * 15)

the_route.add_invoice(invoice, satoshi_count)

route_json = json.dumps(the_route.route_object)

send_cmd = "{lncli} sendtoroute --payment_hash={rhash} --routes='{route}'".format(
    lncli=lncli_cmd, rhash=invoice.r_hash, route=route_json)

if DEBUG:
    print(send_cmd)
    print("-" * 15)
send_command = Commandline(send_cmd)
send_command.run()
if len(send_command.error) > 0:
    print("Failed to send the payment", send_command.error)
    exit(1)
elif len(send_command.output) > 0:
    if '"status": "SUCCEEDED",' in send_command.output:
        print("Success")
        if DEBUG:
            print(send_command.output)
    else:
        print("Unexpected response:")
        print(send_command.output)
        print("-" * 15)
