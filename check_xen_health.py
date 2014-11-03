#!/usr/bin/env python
#check_xen_server - Xen server health check for dc/appliance
#by Joshua Jackson<tsunam@gmail.com>

import os
import subprocess
import pickle
import socket
import time
import struct
import re
import sys
from optparse import OptionParser


def xeinfo():
    #xencluster doesn't make this as easy with just an info event, so need to ask xe multiple different things
    #additionally it returns multi line output from the popen, so need to clean that up, cause citrix can't sanitize their output
    cpuinfo, err = subprocess.Popen("/usr/bin/xe" + " host-cpu-info --minimal", shell=True, stdout=subprocess.PIPE).communicate()
    cpuinfo = cpuinfo.split()
    uuid, err = subprocess.Popen("/usr/bin/xe" + " host-list params=uuid,name-label", shell=True, stdout=subprocess.PIPE).communicate()
    uuid_list = uuid.split()
    host_idx = [i for i, item in enumerate(uuid_list) if re.search(socket.gethostname(), item)]
    #actual uuid for the host is 4 before the hostname
    hostuuid = host_idx[0] - 4
    cmd_total = "/usr/bin/xe host-list params=memory-total uuid=%s --minimal" % (uuid_list[hostuuid])
    memcount, err = subprocess.Popen( cmd_total,shell=True, stdout=subprocess.PIPE).communicate()
    memcount = memcount.split()
    cmd_free = "/usr/bin/xe host-list params=memory-free uuid=%s --minimal" % (uuid_list[hostuuid])
    memfree, err = subprocess.Popen( cmd_free,shell=True, stdout=subprocess.PIPE).communicate()
    memfree = memfree.split()
    return cpuinfo[0], memcount[0], memfree[0]

def xminfo():
	xminfo, err = subprocess.Popen("/usr/sbin/xm " + "info", shell=True, stdout=subprocess.PIPE).communicate()
	lines = xminfo.splitlines()
	#pull useful base hardware info 
	for info in lines:
		words = info.split()
		if "nr_cpus" in words:
			cpucount = words[-1]
		if "total_memory" in words:
			memcount = words[-1]
		if "free_memory" in words:
			freecount = words[-1]
	return cpucount, memcount, freecount

def xentop():
	cpuusage = 0
	memusage = 0
	vcpus =	0
	xentop, err = subprocess.Popen("/usr/sbin/xentop " + "-b" + " -i" + " 1", shell=True, stdout=subprocess.PIPE).communicate()
	lines = xentop.splitlines()
	#skip header line in length query
	vms = len(lines[1:])
	#remove dom0 from number of vm's running
	vms = vms - 1
	#skip header line
	for info in lines[1:]:
		words = info.split()
		cpuusage += float(words[3])
		#memory is measured in kb's but xminfo measures in mbs
		memusage += int(words[4]) / 1024
		#dom0 no limit causes  field 8 to be n/a instead of the dom0 vcpus field
		if "n/a" in words[8]:
			vcpus += 1
		else:
			vcpus += int(words[8])
	return cpuusage, memusage, vcpus, vms

def nagios(cpu, cpuusage, mem, memusage, vcpus, vms, free, vm_slots=10, warning=90, critical=95):
	excode = 0
	cpu_max = cpu * 100
	used_cpu = (float(vcpus)/float(cpu)) * 100
	used_mem = (float(memusage)/float(mem)) * 100
	#we have a limit on the total number of vm's that are allowed to run per cc worker
	if vm_slots != "None":
		slots_used = (float(vms)/float(vm_slots)) * 100
	cpu_percent = (float(cpuusage)/float(cpu_max)) * 100
	vlist = { "used_cpu": used_cpu, "used_mem": used_mem, "slots_used": slots_used, "cpu_percent": cpu_percent }
	for k,v in vlist.iteritems():
		if v > warning and v < critical:
			excode = 1
		elif v > critical:
			excode = 2
		else:
			continue
	print "% Cpu allocated: " + str(round(used_cpu, 2)) +  " % Cpu Used: " + str(round(cpu_percent, 2)) + " % Memory Used: " + str(round(used_mem, 2)) + " Total slots allocated: " + str(vms) + "/" + str(vm_slots)
	sys.exit(excode)

def graph_send(events, carbon_host, carbon_port):
	#pickled data goes to port 2004 instead of 2003 where cleartext goes
	carbon_port = carbon_port + 1
	prefix = "servers." + socket.gethostname() + "."
	pickled = ([])
	epoch = int(time.time())
	for key,value in events.iteritems():
		pickled.append([ prefix + key, [ epoch, value ]])
	payload = pickle.dumps(pickled)
	header = struct.pack("!L", len(payload))
	message = header + payload
	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.connect((carbon_host, carbon_port))
	try:
		s.sendall(message)
	except socket.error, (value,message):
		print "could not send message:", message
		sys.exit(1)
	s.close()	
	
def options():
	parser = OptionParser()
	parser.add_option("-c", "--config", dest="config", help="Axcloud configuration file name", metavar="CONFIG", default="default.yaml")
	parser.add_option("-w", "--warning", type="int", dest="warning", help="nagios warning theshold", metavar="WARNING", default="90")
	parser.add_option("-r", "--critical", type="int", dest="critical", help="Nagios ", metavar="CRITICAL", default="95")
	parser.add_option("-n", "--nagios", action="store_true", dest="nagios", help="Enable nagios checks")
	parser.add_option("-g", "--graphite", action="store_true", dest="graphite", help="Enable sending of data to graphite")
        parser.add_option("-s", "--server", dest="server", help="Graphite server", metavar="SERVER")
        parser.add_option("-p", "--port", type="int", dest="port", help="Graphite pickle port", metavar="PORT", default="2004")
	return parser
	
def main():
	arguments = options()
	(opts, args) = arguments.parse_args()
        if os.path.exists("/etc/redhat-release"):
            if "XenServer" in open('/etc/redhat-release','r').read().split(' ')[0]:
                cpu, mem, free = xeinfo()
        else:
            cpu, mem, free = xminfo()
	cpuusage, memusage, vcpus, vms = xentop()
	values = { "nr_cpus": cpu, "total_memory": mem, "free_memory": free, "cpu_percent": cpuusage, "used_memory": memusage, "virtual_cpus": vcpus, "total_vms": vms }
	if opts.graphite is True:
		graph_send(values, opts.server, opts.port)
	if opts.nagios is True:
		nagios(cpu, cpuusage, mem, memusage, vcpus, vms, free, warning=opts.warning, critical=opts.critical)

if __name__=="__main__":
	main()	
