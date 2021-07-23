import json
import shlex
import subprocess


DEBUG = False
DEBUG_FAILURE = False
FEE_PER_REBALANCE = 20  # In satoshis


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

    def balance_score(self):
        if self.local_balance == 0:
            return 0.0
        if self.remote_balance == 0:
            return 1000.0
        return float(self.remote_balance) / float(self.local_balance)

    def out_of_balance(self):
        score = self.balance_score()
        if score > 8.0 or score < 0.125:
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


which_lncli = Commandline("which lncli")
which_lncli.run()
lncli_cmd = "lncli"
if len(which_lncli.error) > 0:
    print("Failed to determine where lncli is located", which_lncli.error)
    exit(1)
elif len(which_lncli.output) > 0:
    # this should work on non-umbrel nodes (but I haven't tested)
    lncli_cmd = "lncli"
else:
    # docker is for running on the umbrel
    lncli_cmd = "docker exec -it lnd lncli"

if DEBUG:
    print("Using {lncli}".format(lncli=lncli_cmd))

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

balanced_channels = []
unbalanced_channels = []
the_channels = data["channels"]
for channel_record in the_channels:
    one = Channel(channel_record)
    if one.out_of_balance() is True:
        unbalanced_channels.append(one)
    else:
        balanced_channels.append(one)
if len(balanced_channels) > 0:
    print("You have", len(balanced_channels), "that are balanced-enough")
if len(unbalanced_channels) > 0:
    # print("Out of balance: ", len(unbalanced_channels))
    mostly_local = []
    mostly_remote = []
    for one_channel in unbalanced_channels:
        # print(one_channel.remote_pubkey, one_channel.channel_id, one_channel.local_balance,
        # one_channel.remote_balance, one_channel.balance_score())
        if one_channel.remote_balance > one_channel.local_balance:
            mostly_remote.append(one_channel)
        else:
            mostly_local.append(one_channel)

    print("You have", len(mostly_remote), "channels with mostly inbound capacity")
    print("You have", len(mostly_local), "channels with mostly outbound capacity")
    print("We are going to try find routes to balance these channels.")

    # user_input = input('Do you want to use balanced channels to try balancing imbalanced channels? Type y / n ')
    # if user_input.startswith("y") or user_input.startswith("Y"):
    #     use_balanced = True
    # else:
    #     use_balanced = False

    user_input = input('How many sats can we spend for each rebalance transaction? ({fees} sats default) : '.format(
        fees=FEE_PER_REBALANCE))
    if len(user_input) > 0:
        FEE_PER_REBALANCE = int(user_input)
        print("Using {fees} sats as our maximum fee".format(fees=FEE_PER_REBALANCE))

    user_input = input('Do you want to try moving less of the channel (25%)? Type y / n : ')
    if user_input.startswith("y") or user_input.startswith("Y"):
        move_less = True
    else:
        move_less = False

    if len(mostly_local) > 0 and len(mostly_remote) > 0:
        # we have at least one pair we can try to rebalance
        mostly_local.sort(key=lambda x: x.local_balance, reverse=True)
        mostly_remote.sort(key=lambda x: x.remote_balance, reverse=True)
        # lncli addinvoice --expiry 60 --memo "Automatic rebalancing" --amt <>
        # lncli payinvoice --fee_limit 20 --allow_self_payment --outgoing_chan_id <> --last_hop <> <invoice>
        for one_local in mostly_local:
            if move_less is True:
                half_local_capacity = int((one_local.local_balance + one_local.remote_balance) / 4)
            else:
                half_local_capacity = int((one_local.local_balance + one_local.remote_balance) / 2)

            half_local_capacity -= one_local.remote_balance
            outgoing_chan_id = one_local.channel_id
            addinvoice = '{lncli} addinvoice --expiry 180 --memo "Automatic rebalancing" --amt {amount}'.format(
                lncli=lncli_cmd, amount=half_local_capacity)
            # addinvoice = "cat /Users/ray/Desktop/addinvoice.txt"
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
                the_invoice = invoice_json["payment_request"]

            if len(the_invoice) == 0:
                print("Failed to create an invoice")
                exit(2)

            available = 0
            for one_remote in mostly_remote:
                half_remote_capacity = int(one_remote.remote_balance / 2)
                if half_remote_capacity >= half_local_capacity:
                    available += 1

            print("Trying to balance", outgoing_chan_id, "by moving", half_local_capacity)
            print("  There are", available, "channels with enough inbound-capacity")
            action_taken = False
            for one_remote in mostly_remote:
                half_remote_capacity = int(one_remote.remote_balance / 2)
                if half_remote_capacity >= half_local_capacity:
                    remote_pubkey = one_remote.remote_pubkey
                    # This could work for a rebalancing
                    payinvoice = "{lncli} payinvoice --force  --fee_limit {fee_limit} --allow_self_payment " \
                                 "--outgoing_chan_id {channel} --last_hop {remote_pubkey} {invoice}".format(
                        lncli=lncli_cmd, fee_limit=FEE_PER_REBALANCE, channel=outgoing_chan_id,
                        remote_pubkey=remote_pubkey, invoice=the_invoice)
                    if DEBUG:
                        print(payinvoice)
                        print("==" * 15)
                    pay_command = Commandline(payinvoice)
                    pay_command.run()
                    if len(pay_command.error) > 0:
                        if pay_command.exit_code == 1:
                            if "FAILURE_REASON_NO_ROUTE" in pay_command.error:
                                if outgoing_chan_id in pay_command.error:
                                    print("  No route found for", one_remote.channel_id, "- Consider increasing fees.")
                                else:
                                    print("  No route available for using", one_remote.channel_id)
                            else:
                                print("  Could not balance with", one_remote.channel_id)
                            if DEBUG_FAILURE:
                                print("+" * 20)
                                print(pay_command.error)
                                print("+" * 20)
                        else:
                            print("Failed to pay invoice creation", pay_command.error)
                            exit(1)
                    elif len(pay_command.output) > 0:
                        # print("Payment output", pay_command.output)
                        if "Payment status: FAILED" in pay_command.output:
                            # This channel wasn't a good match for the channel we're looking at
                            print("  Could not balance with", one_remote.channel_id)
                        else:
                            print("  Balanced with", one_remote.channel_id, "- Moved",
                                  half_local_capacity, "sats")
                            one_remote.remote_balance -= half_local_capacity
                            one_local.local_balance -= half_local_capacity
                            action_taken = True
                            break

            print("-" * 20)

