# ShowBase
window-type none

# Network:
net-max-write-queue 50000
net-want-threads #f

# MessageDirector:
messagedirector-address 0.0.0.0
messagedirector-port 7100
messagedirector-message-timeout 15.0

# ClientAgent:
clientagent-address 0.0.0.0
clientagent-port 6667
clientagent-connect-address 127.0.0.1
clientagent-connect-port 7100
clientagent-channel 1000
clientagent-max-channels 1000001000
clientagent-min-channels 1000000000
clientagent-dbm-filename databases/database.dbm
clientagent-dbm-mode c
clientagent-version sv1.0.6.9
clientagent-hash-val 3005460305
clientagent-interest-timeout 2.5

# StateServer:
stateserver-connect-address 127.0.0.1
stateserver-connect-port 7100
stateserver-channel 1001

# Database:
database-connect-address 127.0.0.1
database-connect-port 7100
database-channel 1002
database-directory databases/json
database-extension .json
database-max-channels 199999999
database-min-channels 100000000

# DClass:
dc-multiple-inheritance #f
dc-sort-virtual-inheritance #t
dc-sort-inheritance-by-file #f
