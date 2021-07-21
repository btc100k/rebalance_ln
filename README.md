# rebalance_ln

This is a simple python script to try moving sats from mostly-outbound channels to mostly-inbound channels.
If you have 3 channels with only outbound capacity (A,B,C) and 2 channels with only inbound capacity (D,E), this script tries to send funds from
* A->D
* A->E
* B->D
* B->E
* C->D
* C->E 

# How to use
* You ssh this file to your node: (use the same password you use to see the browser UI)
  * `scp rebalance.py umbrel@umbrel.local:/home/umbrel/`
* You ssh into your node: (use the same password you use to see the browser UI)
  * `ssh umbrel@umbrel.local`
* You run the python script:
  * `python3 ./rebalance.py`
 
The script will give you some feedback & ask you some questions:
```
  You have 28 that are balanced-enough
  You have 3 channels with mostly inbound capacity
  You have 11 channels with mostly outbound capacity
  We are going to try find routes to balance these channels.
  How many sats can we spend for each rebalance transaction? (20 sats default) : 
  Do you want to try moving less of the channel (25%)? Type y / n : 
```
Then the script will match your imbalanced channels with inbound liquidity to the imbalanced channels with outbound liquidity.
```
  Trying to balance ####### by moving #####
    There are # channels with enough inbound-capacity
```
This will succeed if you've specified a high-enough fee, and if there is a route available for the sats to flow.
