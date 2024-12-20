# pba-stat
pba-stat is a Junos SRX on-box Python script that provides insights into a specified Port Block Allocation enabled NAT pool for the purpose of tuning PBA parameters (block size and maximum of allocated blocks). Subpar PBA settings can lead to waste of resources, service impact, unnecessary allocation/de-allocation logging, and more. Use cases such as Mobile, xDSL, IoT, and others typically have different settings.

version 0.14

# General information:

- By default pba-stat is constrained to 10.000 PBA records for safety purposes (RE resources).
- Identify existing or configure a representative PBA enabled NAT pool (by using the new NAT pool with limited client scope).
- The PBA record limit can be increased either run-time using `max-blocks` parameter or `MAX_BLOCKS` constant in the code.
- When determining limits for analysis, watch out for RE using swap - memory constraints 
- Script assumes address-persistent or address-pooling paired endpoint/NAT-IP stickiness 
- SRX chassis cluster is considered as well (creates node specific values and utilization accordingly)
- In case of RPC timeouts adjust the `DEV_TIMEOUT` variable 


# Example usage:

`op pba-stat` (would execute if there is only one PBA enabled pool and no chassis cluster) 

`op pba-stat nat-pool [pool-name]` (retrieve stats for specified NAT pool)

`op pba-stat node [0|1]` (in case of chassis cluster node must be selected)

`op pba-stat max-blocks 20000` (to override default limit of 10.000 analyzed blocks)

`op pba-stat port-threshold [threshold]` (print hosts with ports (sessions) >= threshold)

`op pba-stat trace time` (hidden tracing displaying time spent in various steps)

`op pba-stat nat-pool pool-1 max-blocks 20000 node 0` (complete example)

# Example output 
The mostly self-explanatory output below is from a synthetic traffic run. Conclusion of below could be increase of block size from 128 to 256 and overall NAT pool size as well.
```
> op pba-stat nat-pool pool-1 max-blocks 30000    
------------------------------
NAT-IP : #int-hosts/alloc blk    
--------------->
203.0.113.64    : 205/408        // specific NAT pool IP serves 205 endpoints with 408 allocated blocks
203.0.113.65    : 205/405
<SNIP>
203.0.113.126   : 204/407
203.0.113.127   : 204/405
------------------------------
Int-hosts per NAT-IP stats       // stats of maximum/minimum/avg number of hosts using one NAT pool IP
--------------->
max             : 205            
min             : 204
avg             : 204.80
------------------------------
Blk per NAT-IP
--------------->
capacity        : 504            // maximum blocks per NAT IP
max used        : 411            // current maximum used
min used        : 402
avg used        : 407.75
------------------------------
PBA pool stats
--------------->
blk size        : 128
maximum blk     : 4
total blk       : 32256
allocated blk   : 26096
utilization     : 80.9%
------------------------------
Int-host stats
--------------->
unique hosts    : 13107          
avg blk         : 1.99
total sess      : 2043455        // session terminology instead of ports (e.g., GRE doesn't have port)
max sess        : 204            // maximum number of sessions per endpoint (trigger to look-up using port-threshold)
avg sess        : 155.9          // average sessions per endpoint
------------------------------
Stats per alloc blk cohort 
--------------->
blk/hosts       : 1/177          // 177 endpoints have 1 block
blk/hosts       : 2/12871        // 12871 endpoints 2 blocks
blk/hosts       : 3/59
----------------
blk/percent     : 1/1.4%         // percentual representation of above
blk/percent     : 2/98.2%
blk/percent     : 3/0.5%
----------------
blk/max sess    : 1/128          // endpoints with 1 block have max of 128 sessions
blk/max sess    : 2/204          // endpoints with 2 blocks have max of 204 sessions
blk/max sess    : 3/195
----------------
blk/avg sess    : 1/124          // endpoints with 1 block have on avg 124 sessions
blk/avg sess    : 2/156          // endpoints with 2 blocks have on avg 156 sessions
blk/avg sess    : 3/171 
------------------------------
```
# Installation 

place `pba-stat.py` to 
`/var/db/scripts/op/`

Junos side configuration, consider using Junos group:

`edit groups op-pba-stat`

```
set system scripts op file pba-stat.py command pba-stat
set system scripts op file pba-stat.py arguments nat-pool description "PBA enabled NAT pool name if more than one are defined"
set system scripts op file pba-stat.py arguments node description "Node [0|1] in case of chassis cluster"
set system scripts op file pba-stat.py arguments port-threshold description "print hosts with ports >= threshold"
set system scripts op file pba-stat.py arguments max-blocks description "override MAX_BLOCKS constant for finding platform maximum for stats"
set system scripts language python3
```

To avoid the `CSCRIPT_SECURITY_WARNING` event log regarding unsigned script execution

`set system scripts op file pba-stat.py checksum sha-256` + output from: `% sha256 pba-stat.py`

Apply the group when used

`set apply-groups op-pba-stat`



