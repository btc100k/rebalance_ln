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

    # % that is remote
    def balance_ratio(self):
        if self.local_balance == 0:
            return 0.0
        if self.remote_balance == 0:
            return 1.0

        # this gets me a number between 0 & 1
        total = self.remote_balance + self.local_balance
        return float(self.remote_balance) / float(total)

    def out_of_balance(self):
        balance_ratio = self.balance_ratio()
        if balance_ratio > 0.7 or balance_ratio < 0.3:
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


def pay_invoice_for_sats_to_remote(invoice, sats, remote):
    total_capacity = remote.remote_balance + remote.local_balance
    # This is how much we can move before we move beyond 50%
    half_capacity = total_capacity / 2
    # Allow ourselves overshoot balanced: 55% - 45% (local/remote)
    half_capacity = half_capacity * 1.1
    movement_capacity = half_capacity - remote.local_balance
    if movement_capacity >= sats:
        remote_pubkey = remote.remote_pubkey
        # This could work for a rebalancing
        payinvoice = "{lncli} payinvoice --force  --fee_limit {fee_limit} --allow_self_payment " \
                     "--outgoing_chan_id {channel} --last_hop {remote_pubkey} {invoice}".format(
            lncli=lncli_cmd, fee_limit=FEE_PER_REBALANCE, channel=outgoing_chan_id,
            remote_pubkey=remote_pubkey, invoice=invoice)
        if DEBUG:
            print(payinvoice)
            print("==" * 15)
        pay_command = Commandline(payinvoice)
        pay_command.run()
        if len(pay_command.error) > 0:
            if pay_command.exit_code == 1:
                if "FAILURE_REASON_NO_ROUTE" in pay_command.error:
                    if outgoing_chan_id in pay_command.error:
                        print("  No route found for", remote.channel_id, "- Consider increasing fees.")
                    else:
                        print("  No route available for using", remote.channel_id)
                else:
                    print("  Could not balance with", remote.channel_id)
                if DEBUG_FAILURE:
                    print("+" * 20)
                    print(pay_command.error)
                    print("+" * 20)
            else:
                print("Failed to pay invoice creation", pay_command.error)
                exit(1)
            return 0
        elif len(pay_command.output) > 0:
            # print("Payment output", pay_command.output)
            if "Payment status: FAILED" in pay_command.output:
                # This channel wasn't a good match for the channel we're looking at
                print("  Could not balance with", remote.channel_id)
                return 0
            else:
                print("  *** Balanced with", remote.channel_id, "- Moved", sats, "sats")
                return sats
    else:
        return 0


def create_invoice(amt):
    addinvoice = '{lncli} addinvoice --expiry 600 --memo "Automatic rebalancing" --amt {amount}'.format(
        lncli=lncli_cmd, amount=amt)
    # addinvoice = "cat /Users/ray/Desktop/addinvoice.txt"
    if DEBUG:
        print(addinvoice)
        print("-" * 15)
    add_command = Commandline(addinvoice)
    add_command.run()
    invoice_string = ""
    if len(add_command.error) > 0:
        print("Failed to run invoice creation", add_command.error)
        exit(1)
    elif len(add_command.output) > 0:
        invoice_json = json.loads(add_command.output)
        invoice_string = invoice_json["payment_request"]

    if len(invoice_string) == 0:
        print("Failed to create an invoice")
        exit(2)
    return invoice_string


def count_channels_with_capacity(channels, amt):
    matching = 0
    for check_channel in channels:
        remote_capacity = int(check_channel.remote_balance / 2)
        if remote_capacity >= amt:
            matching += 1
    return matching


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
        result_array.append(Channel(channel_record))

    return result_array


lncli_cmd = get_lncli()
if DEBUG:
    print("Using {lncli}".format(lncli=lncli_cmd))
all_channels = get_channels()

balanced_channels = []
unbalanced_channels = []
for one in all_channels:
    if DEBUG:
        print(one.remote_pubkey, one.remote_balance, one.local_balance, one.balance_ratio(), one.out_of_balance())
    if one.out_of_balance() is True:
        unbalanced_channels.append(one)
    else:
        balanced_channels.append(one)

if len(balanced_channels) > 0:
    print("You have", len(balanced_channels), "that are balanced-enough")

if len(unbalanced_channels) > 0:
    mostly_local = []
    mostly_remote = []
    for one_channel in unbalanced_channels:
        if one_channel.remote_balance > one_channel.local_balance:
            mostly_remote.append(one_channel)
        else:
            mostly_local.append(one_channel)

    print("You have", len(mostly_remote), "channels with mostly inbound capacity")
    print("You have", len(mostly_local), "channels with mostly outbound capacity")
    print("We are going to try find routes to balance these channels.")

    user_input = input('How many sats can we spend for each transaction? ({fees} sats default) : '.format(
        fees=FEE_PER_REBALANCE))
    if len(user_input) > 0:
        FEE_PER_REBALANCE = int(user_input)
    print("Using {fees} sats as our maximum fee".format(fees=FEE_PER_REBALANCE))
    print("")

    user_input = input('Do you want to try moving 25% of the channel capacity? Type y / n : ')
    print("")
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
                payment_amount = int((one_local.local_balance + one_local.remote_balance) / 4)
            else:
                payment_amount = int((one_local.local_balance + one_local.remote_balance) / 2)
                if one_local.remote_balance < payment_amount:
                    payment_amount -= one_local.remote_balance

            outgoing_chan_id = one_local.channel_id
            if payment_amount <= 0:
                print("-------> ", one_local.remote_pubkey,
                      "Remote", one_local.remote_balance,
                      "Local", one_local.local_balance,
                      "Target move", payment_amount)
                continue

            the_invoice = create_invoice(payment_amount)

            available = count_channels_with_capacity(mostly_remote, payment_amount)
            print("Trying to balance", outgoing_chan_id, "by moving", payment_amount)
            print("  There are", available, "channels with enough inbound-capacity")

            used_remote_channel = None
            for one_remote in mostly_remote:
                paid_total = pay_invoice_for_sats_to_remote(the_invoice, payment_amount, one_remote)
                if paid_total > 0:
                    used_remote_channel = one_remote
                    one_remote.remote_balance -= paid_total
                    one_remote.local_balance += paid_total
                    one_local.local_balance -= paid_total
                    one_local.remote_balance += paid_total
                    break

            if used_remote_channel is not None and (used_remote_channel.balance_ratio() <= 0.35):
                print("  ", used_remote_channel.channel_id, "is now balanced enough.",
                      "Remote ratio", used_remote_channel.balance_ratio())
                mostly_remote.remove(used_remote_channel)
            else:
                # Can se skim a little off of our balanced channels?
                for one_balanced in balanced_channels:
                    # 60% + is remote
                    if one_balanced.balance_ratio() > 0.6:
                        paid_total = pay_invoice_for_sats_to_remote(the_invoice, payment_amount, one_balanced)
                        if paid_total > 0:
                            one_balanced.remote_balance -= paid_total
                            one_balanced.local_balance += paid_total
                            one_local.local_balance -= paid_total
                            one_local.remote_balance += paid_total
                            break
            print("-" * 20)
