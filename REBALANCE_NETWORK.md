# rebalance_network.py

This is a simple python script looks through your channels and their channels and so on.
Any node which requires too many hops to route sats through will be offered as a candidate for a new channel.

# How to use
* You ssh this file to your node: (use the same password you use to see the browser UI)
  * `scp rebalance_network.py umbrel@umbrel.local:/home/umbrel/`
* You ssh into your node: (use the same password you use to see the browser UI)
  * `ssh umbrel@umbrel.local`
* You run the python script:
  * `python3 ./rebalance_network.py`

The script will ask you to pick the shortest route to highlight as worthy of opening a new channel.
The script will also ask if you want to exclude channels smaller than a certain size (in sats).
```
We're going to look at all the channels of the nodes to which you have outbound channels
   we're looking for nodes which are distant to you.
If you had a direct connection to a sufficiently distant node, 
   you'll cut the path in half to any node on the route.
++++++++++++++++++++
What is the shortest route to consider?: (Default: 6) 
Minimum channel capacity to consider nodes?: (Default: 500000) 
```

The script will then start making network calls looking at your channels:
```
Collecting information on your channels: ##
++++++++++++++++++++
```

The script then looks at all the channels of the nodes to which you have channels:
```
Collecting channels for level 2 nodes: ##
++++++++++++++++++++
```

The script then looks at the channels of the nodes to the nodes to which you have channels:
```
Collecting channels for level 3 nodes: ###
++++++++++++++++++++
```

This is where the script starts getting interesting.

Depending upon the minimum route length you chose, you should soon start seeing suggestions for nodes to connect to:
```
   Here is a good candidate node: ####################################################################
   Alias: Reptilian Banking Cartel
   Link: https://1ml.com/node/####################################################################
   Addr: ####################################################################@##############################################
   Channels: 16
   Total Capacity: 0.82 BTC
   Number of hops: 6
---------------------------------
```
The idea is to find a long route and cut it down to size by making a direct channel to this distant node.

Quit the program by spamming Control-C.
