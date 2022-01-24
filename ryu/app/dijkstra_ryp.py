from ryu.base import app_manager
from ryu.controller import mac_to_port
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.mac import haddr_to_bin
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from ryu.lib import mac
 
from ryu.topology.api import get_switch, get_link
from ryu.app.wsgi import ControllerBase
from ryu.topology import event, switches
from collections import defaultdict
 
# switches
# list of all switches in our topology
switches = []
 
# mymac[srcmac]->(switch, port)
# MAC (media access control address) is a unique identifier assigned to a network interface controller. 
# MAC addresses are used in the medium access control protocol sublayer of the data link layer.
# Here we use mac as a key for src of ethenet with values (switch, port) which switch declares datapath_id and 
# port declares in_port (in_port is declared inside message)
mymac={}
 
# adjacency map [sw1][sw2]->port from sw1 to sw2
# This means that if there is a port (portx) between switch1 and switch2, the value of 
# adjacency[sw1][sw2] = portx, else it will be None.
adjacency=defaultdict(lambda:defaultdict(lambda:None))
 
def minimum_distance(distance, Q):
  print("... minimum distance function is called ...")
  min = float('Inf') # infinite number
  node = -1 # default value
  for v in Q: # checks in all nodes in Q(set) to find the minimum distance, and then return it.
    if node == -1:
        node = v
        min = distance[v]
    if distance[v] < min:
      min = distance[v]
      node = v
  return node
 
def get_path (src,dst,first_port,final_port):
  
  # this function is called inside "_packet_in_handler()" which is called every 
  # "EventOFPPacketIn" is triggered.
  
  # inputs {src: datapath id of current source mac | dst: datapath id of current destination mac
  # first_port: port_in of current source mac | final_port: port_in of current source mac}
  # Dijkstra's algorithm
  print ("get_path() is called, src=",src," dst=",dst, " first_port=", first_port, " final_port=", final_port)
  distance = {} # a dictionary to store distance from "src" to every node. 
  previous = {} # just to handle dijkstra algorithm.
  for dpid in switches: # initialization for both "distance" = all "inf" and "previous" = all "None"
    distance[dpid] = float('Inf')
    previous[dpid] = None
 
  distance[src]=0 # we want to measure distance from src node
  Q=set(switches) # set of all switches
  print ("Q=", Q)

  while len(Q)>0: # implementation of dijkstra: continue until you see all nodes in the graph.
    u = minimum_distance(distance, Q) # u: node with smallest distance till now.
    Q.remove(u)
   
    for p in switches: 
      if adjacency[u][p]!=None: #for all adjacent nodes with "u"
        w = 1 # default weight for edge: 1, because we assume that all edges (links) have same time consumption ***bug*** : weights might not be all 1 and equal
        if distance[u] + w < distance[p]: 
          
          # if it's possible to update "distance" for adjecents with "u" 
          # with less values, then update it
          distance[p] = distance[u] + w
          previous[p] = u
 
  print(distance)
  
  # after performing dijkstra : 
  r=[] # a list to store path from src to dst (in an inverse way: dst -> ... -> src)
  p=dst # every node we want to add to path
  r.append(p) # first node we add to r: dst
  q=previous[p] # to store "previous node in path from dst to src which" mean "next in path from src to dst"
  while q is not None: 
    # while you haven't reached src
    
    if q == src: #src reached : end of while
      r.append(q)
      break
    p=q
    r.append(p) # appending to path
    q=previous[p]
 
  r.reverse() # reverse "dst to src" to "src to dst"
  if src==dst: # if path length is 1 (only src itself)
    path=[src]
  else:
    path=r
 
  # Now add the ports
  r = []
  in_port = first_port
  for s1,s2 in zip(path[:-1],path[1:]): #for example:(a,b,c,d) iterations:  (a,b), (b,c), (c,d)
    
    # per every node s1 we store port from s1 to s2(next) and s1 to previous (it means that for s2 previous is s1)
    out_port = adjacency[s1][s2]
    r.append((s1,in_port,out_port))
    in_port = adjacency[s2][s1]
  r.append((dst,in_port,final_port))
  
  print("... path: ", r)
  print()
  return r # a list of (node, previous port path, next port in path)
 
class ProjectController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    # Ryu supports openflow versions 1, 1.2, 1.3, 1.4, 1.5, so we store them in "OFP_VERSIONS"
    def __init__(self, *args, **kwargs):
          
        print("... controller created ...")
        print()
        super(ProjectController, self).__init__(*args, **kwargs)
        self.mac_to_port = {} 
        # mac to port is a dictionary to map mac addresses to ports, but as we use 
        # "mymac" dictionary instead, this dict:"mac_to_port" is useless.
        
        self.topology_api_app = self
        self.datapath_list=[] # list of all datapathes (every switch has a datapath)
  
    # Handy function that lists all attributes in the given object
    
    def ls(self,obj): # just a simple function to print info
        print("\n".join([x for x in dir(obj) if x[0] != "_"]))

    def add_flow(self, datapath, in_port, dst, actions): 
    # -> ***redundant*** : this function is never used
    
        print("... add_flow() called ...")
        ofproto = datapath.ofproto # declares openflow version
        parser = datapath.ofproto_parser # different versions have different apis, so we use parser to use the correct one
        match = datapath.ofproto_parser.OFPMatch(in_port=in_port, eth_dst=dst) 
        # there are different packets with different priorities, if current packet doesn't match our priorities
        # by default it will be sent to the controller to be handled.
        
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)] 
        # inst consists of "an action and a mode" used as a prerequisite in sending message
 
        # here we set priority to "OFP_DEFAULT_PRIORITY = 32768"
        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath, match=match, cookie=0,
            command=ofproto.OFPFC_ADD, idle_timeout=0, hard_timeout=0,
            priority=ofproto.OFP_DEFAULT_PRIORITY, instructions=inst)
        
        # in order to modify "table flow" of a switch we build an "OFPFlowMod" object and pass
        # match, inst, priority of packets, and datapath to it.
        datapath.send_msg(mod) #sending message with mod information
 
    def install_path(self, p, ev, src_mac, dst_mac):
          
       # is called inside "_packet_in_handler()" when destination is valid inside "mymac"
       # this function sends message through the path from src to dst
       
       # inputs = {p: path from src to dst | ev: event that triggers "_packet_in_handler()"
       # src_mac: source of path | dst_mac: destination of path}
       print ("install_path is called")
       
       msg = ev.msg # message of current event
       datapath = msg.datapath 
       # datapath of current message which consists of attributes which declares information about msg
       # such as id of sender, ofproto which is related to version and ...       
       ofproto = datapath.ofproto # declares openflow version
       parser = datapath.ofproto_parser #different versions have different apis, so we use parser to use the correct one
       print("start sending message through path: ")
       for sw, in_port, out_port in p: # sends msg through the path 
        print(sw , end=" ")
        match=parser.OFPMatch(in_port=in_port, eth_src=src_mac, eth_dst=dst_mac)
        # creates its match (described in "add_flow()")
        actions=[parser.OFPActionOutput(out_port)]
        # declares openflow action (says what to do after matching)
        
        for dpi in self.datapath_list:
          if dpi.id == sw:
            datapath = dpi
        # datapath=self.datapath_list[int(sw)-1] 
        # -> ***bug:*** this part of code had a bug so we replaced it : sw value may not be equal to datapath_list index
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS , actions)]
        # creates its inst ( described in "add_flow()")

        #here we set priority = 1
        mod = datapath.ofproto_parser.OFPFlowMod(
        datapath=datapath, match=match, idle_timeout=0, hard_timeout=0,
        priority=1, instructions=inst)
        # creates its inst ( described in "add_flow()")
        datapath.send_msg(mod)
       print("... end of path ...")
 
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures , CONFIG_DISPATCHER)
    def switch_features_handler(self , ev):
        
        # every messشge transfer between switch and controller triggers an action which calls this function
        # these requests and response works over openflowProtocol and contains a message
        # every time a switch enters the network, this event triggers.
        print ("switch_features_handler is called")
        datapath = ev.msg.datapath # datapath of current message (described in "install_path")
        # all the beneath declarations described in "install_path"
        ofproto = datapath.ofproto 
        parser = datapath.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS ,actions)]
        
        # here we set priority = 0 to set a minimum priority for the times packet priority could not be found 
        # and we should sent it to controller
        mod = datapath.ofproto_parser.OFPFlowMod(
        datapath=datapath, match=match, cookie=0,
        command=ofproto.OFPFC_ADD, idle_timeout=0, hard_timeout=0,
        priority=0, instructions=inst)
        datapath.send_msg(mod)
 
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
          
        # print("_packet_in_handler() is called")
          
        # this function is called every time a packer is received (using "EventOFPPacketIn" to check)
        
        #these declarations described previously
        msg = ev.msg  
        
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        in_port = msg.match['in_port']
        # sets in_port: port which sent current packet to this switch (receiver switch)

        pkt = packet.Packet(msg.data)
        # fetching packet from msg
        eth = pkt.get_protocol(ethernet.ethernet)
        # fetching ethernet from packet protocol 
        
        
        # avoid broadcast from LLDP
        
        # The Link Layer Discovery Protocol is a vendor-neutral link layer protocol used by network devices for advertising 
        # their identity, capabilities, and neighbors on a local area network based on IEEE 802 technology, 
        # principally wired Ethernet.
        
        # In order to avoid cyclic and infinite sends, we avoid broadcasting LLDP
        if eth.ethertype==35020:
            return
          
        # print("ether type : ", eth.ethertype)
 
        
        dst = eth.dst
        # destination of ethernet
        src = eth.src
        # source of ethernet
        dpid = datapath.id
        # setting datapath id to use as switch inside mymac
        self.mac_to_port.setdefault(dpid, {}) 
        # if dpid was not valid, return an empty dict instead
        # -> ***redundant*** : this function is useless and does nothing
        if src not in mymac.keys(): # if src is new, add it in mymac (key: src, dpid: switch, in_port: port)
            mymac[src]=( dpid,  in_port)

        if dst in mymac.keys(): 
            # if destination is valid, then call "get_path()" to get best path using dijkstra
            # then call "install_path()" to send message through path
            p = get_path(mymac[src][0], mymac[dst][0], mymac[src][1], mymac[dst][1])
            print (p)
            self.install_path(p, ev, src, dst)
            out_port = p[0][2]
        else:
            #if destination is not valid, broadcast it using flooding (send to all except for sender)
            out_port = ofproto.OFPP_FLOOD
        actions = [parser.OFPActionOutput(out_port)]
        # set action based on out_port
 
        # install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD:
            # if out_port was not set for flooding, set match (match described in "install_path()")
            match = parser.OFPMatch(in_port=in_port, eth_src=src, eth_dst=dst)
            # -> ***redundant*** : "match" is never used
       
        data=None
        #if message is not buffered and it could be send via 1 packet, then set data, otherwise data would be None 
        # and the message would be sent through another way.
        if msg.buffer_id==ofproto.OFP_NO_BUFFER:
           data=msg.data
 
        # OFPPacketOut class is used to build a packet_out message.
        out = parser.OFPPacketOut(
            datapath=datapath, buffer_id=msg.buffer_id, in_port=in_port,
            actions=actions, data=data)
        #sends message
        datapath.send_msg(out)
    
    @set_ev_cls(event.EventSwitchEnter)
    # The event EventSwitchEnter will trigger the activation of get_topology_data().
    # there are EventSwitchEnter and EventSwitchLeave events. here we used EventSwitchEnter 
    # to get all links. Links on a switch will be discovered after Ryu found that switch.
    def get_topology_data(self, ev):
          
        print("get_topology_data() is called")
        global switches
        switch_list = get_switch(self.topology_api_app, None)
        # fetching all switches from current topology  
        switches=[switch.dp.id for switch in switch_list]
        # fetching all datapath ids from switch_list
        self.datapath_list=[switch.dp for switch in switch_list]
        # fetching all datapaths from switch_list

        print ("switches=", switches)

        links_list = get_link(self.topology_api_app, None)
        #fetch all links from topology
        mylinks=[(link.src.dpid,link.dst.dpid,link.src.port_no,link.dst.port_no) for link in links_list]
        print(mylinks)
        # per every link in links_list, store datapath_id of src and dst and 
        # port number of src and dst in mylinks (important values)
        for s1,s2,port1,port2 in mylinks: #fill the adjacency map with valid values (used in dijkstra later, and ...)
          adjacency[s1][s2]=port1
          adjacency[s2][s1]=port2
        print(adjacency)
        