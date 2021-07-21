# rebalance_fees.py

This is a simple python script to adjust the fees on a per channel basis.
You set the base fee you want on all channels.

# How to use
* You ssh this file to your node: (use the same password you use to see the browser UI)
  * `scp rebalance_fees.py umbrel@umbrel.local:/home/umbrel/`
* You ssh into your node: (use the same password you use to see the browser UI)
  * `ssh umbrel@umbrel.local`
* You run the python script:
  * `python3 ./rebalance_fees.py`

The script will give you some feedback & ask you some questions:
```
You have 25 channels that are mostly balanced
You have 3 channels with mostly inbound capacity
You have 15 channels with mostly outbound capacity
We are going to:
   -- raise fees on mostly-outbound channels
   -- lower fees on mostly-inbound channels
   -- reset fees on mostly-balanced channels
What would you like your base fee to be? [format: base,ppm,timelock] (1000,1,40 sats default) : 
```
Enter your base fee, ppm fee, and timelock delta. No need for spaces between commas. You can skip the timelock if you like 40.

The script will take your base fees and increase/decrease based upon how far out of balance the channel is.
The script considers the channel as balanced if 25% - 75% of the capacity is on your side.
If the channel is out of balance the distance from 50%/50% is used to scale your base fee.
For example:
* Channel capacity 2,000,000 with 0 remote. 50% - 0% = 50%. <Your Fee> * 0.50 = <New Fee>
* Channel capacity 2,000,000 with 0 local. 100% - 50% = 50%. <Your Fee> / 0.50 = <New Fee>
* Channel capacity 2,000,000 with 250,000 remote. . 50% - 12.5% = 37.5%. <Your Fee> * 0.375 = <New Fee>
```
Using ###,### sats as our base fee, with ## as the timelock.
##### out of balance #### ####
   Current fees ### ###
   Updating fees to ### ###
--------------------
```
