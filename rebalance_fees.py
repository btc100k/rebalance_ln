import json
import shlex
import subprocess

DEBUG = False
DEBUG_FAILURE = False
DEFAULT_BASE_FEE = 1000
DEFAULT_BASE_PPM = 1
DEFAULT_TIMELOCK = 40


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
        self.base_fee_msat = DEFAULT_BASE_FEE
        self.ppm_fee = DEFAULT_BASE_PPM

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

    update_channel_fees(result_array)
    return result_array


def update_channel_fees(channel_list):
    feereport = '{lncli} feereport'.format(lncli=lncli_cmd)
    if DEBUG:
        print(feereport)
        print("-" * 15)
    data = {}
    fee_cmd = Commandline(feereport)
    fee_cmd.run()
    if len(fee_cmd.error) > 0:
        print("Failed to get channel fees", fee_cmd.error)
        exit(1)
    elif len(fee_cmd.output) > 0:
        data = json.loads(fee_cmd.output)
    else:
        print("No channels found")
        exit(2)

    channel_point_map = {}
    for one in channel_list:
        channel_point_map[one.channel_point] = one

    channel_fees = data["channel_fees"]
    for fee_record in channel_fees:
        channel_point = fee_record["channel_point"]
        if channel_point in channel_point_map:
            one = channel_point_map[channel_point]
            one.base_fee_msat = int(fee_record["base_fee_msat"])
            one.ppm_fee = int(fee_record["fee_per_mil"])


lncli_cmd = get_lncli()
all_channels = get_channels()

balanced_channels = []
unbalanced_channels = []
mostly_local = []
mostly_remote = []
for one_channel in all_channels:
    if one_channel.out_of_balance() is True:
        unbalanced_channels.append(one_channel)
        if one_channel.remote_balance > one_channel.local_balance:
            mostly_remote.append(one_channel)
        else:
            mostly_local.append(one_channel)
    else:
        balanced_channels.append(one_channel)

print("You have", len(balanced_channels), "channels that are mostly balanced")
print("You have", len(mostly_remote), "channels with mostly inbound capacity")
print("You have", len(mostly_local), "channels with mostly outbound capacity")
print("We are going to:")
print("   -- raise fees on mostly-outbound channels")
print("   -- lower fees on mostly-inbound channels")
print("   -- reset fees on mostly-balanced channels")

user_base = DEFAULT_BASE_FEE
user_ppm = DEFAULT_BASE_PPM
user_timelock = DEFAULT_TIMELOCK
user_input = input('What would you like your base fee to be? [base,ppm,time lock format]'
                   ' ({base},{ppm},{timelock} sats default) : '.format(
                   base=user_base, ppm=user_ppm, timelock=user_timelock))
if len(user_input) > 0:
    two_words = user_input.split(',')
    if len(two_words) == 1:
        user_base = int(two_words[0])
    elif len(two_words) == 2:
        user_base = int(two_words[0])
        user_ppm = int(two_words[1])
    elif len(two_words) == 3:
        user_base = int(two_words[0])
        user_ppm = int(two_words[1])
        user_timelock = int(two_words[2])

if user_base <= 0:
    user_base = 0
if user_ppm <= 0:
    user_ppm = 0
if user_timelock <= 0:
    user_timelock = DEFAULT_TIMELOCK

print("Using {base},{ppm} sats as our base fee, "
      "with {timelock} as the timelock.".format(
      base=user_base, ppm=user_ppm, timelock=user_timelock))

for unbalanced in unbalanced_channels:
    score = unbalanced.balance_ratio()
    if score > 0.50:
        # mostly remote
        # We want to raise fees

        # adjusted_score is the amount out of balance we are
        adjusted_score = score - 0.50
        # range 0.50 - 0.25
        adjusted_base = int(float(user_base) / float(adjusted_score))
        adjusted_ppm = int(float(user_ppm) / float(adjusted_score))
    else:
        # mostly local
        # we want to lower fees

        # adjusted_score is the amount out of balance we are
        adjusted_score = 0.50 - score

        # range 0.50 - 0.25
        adjusted_base = int(float(user_base) * float(adjusted_score))
        adjusted_ppm = int(float(user_ppm) * float(adjusted_score))

    print(unbalanced.channel_id, "out of balance", unbalanced.local_balance,
          unbalanced.remote_balance)  # .format(base=user_base, ppm=user_ppm)
    print("   Current fees", unbalanced.base_fee_msat, unbalanced.ppm_fee)
    print("   Updating fees to", adjusted_base, adjusted_ppm)
    udpatefee = '{lncli} updatechanpolicy --base_fee_msat {base_fee} ' \
                '--fee_rate {ppm_fee} --time_lock_delta {timelock} --chan_point {channel_point}'.format(
                lncli=lncli_cmd, base_fee=adjusted_base, ppm_fee=(float(adjusted_ppm)/1000000),
                channel_point=unbalanced.channel_point, timelock=user_timelock)
    if DEBUG:
        print(udpatefee)
        print("-" * 15)
    update_fee_command = Commandline(udpatefee)
    update_fee_command.run()
    if len(update_fee_command.error) > 0:
        print("Failed to update fee", update_fee_command.error)
        exit(1)
    print("-" * 20)


for balanced in balanced_channels:
    print(balanced.channel_id, "is mostly balanced", balanced.local_balance,
          balanced.remote_balance)
    print("   Current fees", balanced.base_fee_msat, balanced.ppm_fee)
    print("   Updating fees to", user_base, user_ppm)
    udpatefee = '{lncli} updatechanpolicy --base_fee_msat {base_fee} ' \
                '--fee_rate {ppm_fee} --time_lock_delta {timelock} --chan_point {channel_point}'.format(
        lncli=lncli_cmd, base_fee=user_base, ppm_fee=(float(user_ppm)/1000000),
        channel_point=balanced.channel_point, timelock=user_timelock)
    if DEBUG:
        print(udpatefee)
        print("-" * 15)
    update_fee_command = Commandline(udpatefee)
    update_fee_command.run()
    if len(update_fee_command.error) > 0:
        print("Failed to update fee", update_fee_command.error)
        exit(1)
    print("-" * 20)
