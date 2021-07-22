# rebalance_ring.py

This is a simple python script to balance a ring of nodes.

# How to use
* You ssh this file to your node: (use the same password you use to see the browser UI)
  * `scp rebalance_ring.py umbrel@umbrel.local:/home/umbrel/`
* You ssh into your node: (use the same password you use to see the browser UI)
  * `ssh umbrel@umbrel.local`
* You run the python script:
  * `python3 ./rebalance_ring.py`
 
The script will give you some feedback & ask you some questions. Enter the pubkeys of the nodes you want to balance, in the ring's order. Add your node's pubkey last.
```
Enter all of the node ids in your ring.
Start with the node where you have outbound liquidity.
End with your node.
---------------------------------------------------------
Signal that you're done entering nodes with a blank line.
---------------------------------------------------------
Enter a node id (remote pubkey): ##################################################################
Enter a node id (remote pubkey): ##################################################################
Enter a node id (remote pubkey): ##################################################################
Enter a node id (remote pubkey): 
```

Then the script will ask how many satoshis you want to send.
The default value is the excess you have locally which would make the channel balanced.
If this is the right amount, just press return.
```
How many satoshis do you want to send? (Default: #####) #######
---------------------------------------------------------
```

Then the script will as you which channel you want the funds to originate from.
Assuming you added the nodes in the ring's connection order, the default should be the right channel.
If this is the right channel, just press return.
```
From what channel will the funds originate? (Default: 759630593454637056) 
---------------------------------------------------------
```

Then the script will as you how much you're willing to pay in fees for the rebalance.
If your max fee is too low, you will be shown the fee needed.
```
What is the maximum fee you're willing to pay in satoishis? (Default: 50) #
---------------------------------------------------------
```

That is it.
```
Success
################################################################## charged 46650 msats
################################################################## charged 373 msats
################################################################## charged 0 msats
```


