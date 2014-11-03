check_xen_health.py
================

Script to get basic health information from either xenserver, or xen hosts. 

---

If you are using this from within a utility such as nrpe, ensure that the user that it is run under has access to run the expected utilities (xm/xe, xentop)

---

Example Usage:

command[check_xen_health]=/usr/bin/sudo /usr/lib/nagios/plugins/check_xen_health.py -g -n -s graphite.example.com -p 2004

Example Output:

% Cpu allocated: 50.0 % Cpu Used: 1.2 % Memory Used: 42.8 Total slots allocated: 8/10

