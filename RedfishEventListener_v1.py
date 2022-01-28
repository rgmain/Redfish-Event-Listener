# Copyright Notice:
# Copyright 2017-2019 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Event-Listener/blob/master/LICENSE.md

import socket
import traceback
import logging
import json
import ssl
from datetime import datetime
import sys
import re

import requests
import threading
from http_parser.http import HttpStream
from http_parser.reader import SocketReader

from redfish import redfish_client, AuthMethod
import redfish_utilities.event_service as event_service

my_logger = logging.getLogger()
my_logger.setLevel(logging.DEBUG)
standard_out = logging.StreamHandler(sys.stdout)
standard_out.setLevel(logging.INFO)
my_logger.addHandler(standard_out)

tool_version = '1.0.3'

config = {
    'listenerip': '0.0.0.0',
    'listenerport': 443,
    'usessl': True,
    'certfile': 'cert.pem',
    'keyfile': 'server.key',
    'destination': 'https://contoso.com',
    'eventtypes': ['Alert'],
    'contextdetail': 'Public',
    'protocol': 'Redfish',
    'subscriptionURI': '/redfish/v1/EventService/Subscriptions',
    'serverIPs': [],
    'usernames': [],
    'passwords': [],
    "logintype": [],
    'certcheck': True,
    'verbose': False
}

### Function to read data in json format using HTTP Stream reader, parse Headers and Body data, Response status OK to service and Update the output into file
def process_data(newsocketconn, fromaddr):
    if useSSL:
        connstreamout = context.wrap_socket(newsocketconn, server_side=True)
    else:
        connstreamout = newsocketconn
    ### Output File Name
    outputfile = "Events_" + str(fromaddr[0]) + ".txt"
    logfile = "TimeStamp.log"
    global event_count, data_buffer
    outdata = headers = HostDetails = ""
    try:
        try:
            ### Read the json response using Socket Reader and split header and body
            r = SocketReader(connstreamout)
            p = HttpStream(r)
            headers = p.headers()
            my_logger.info("headers: ", headers)

            if p.method() == 'POST':
                bodydata = p.body_file().read()
                bodydata = bodydata.decode("utf-8")
                my_logger.info("\n")
                my_logger.info("bodydata: ", bodydata)
                data_buffer.append(bodydata)
                for eachHeader in headers.items():
                    if eachHeader[0] == 'Host' or eachHeader[0] == 'host':
                        HostDetails = eachHeader[1]

                ### Read the json response and print the output
                my_logger.info("\n")
                my_logger.info("Server IP Address is ", fromaddr[0])
                my_logger.info("Server PORT number is ", fromaddr[1])
                my_logger.info("Listener IP is ", HostDetails)
                my_logger.info("\n")
                outdata = json.loads(bodydata)
                if 'Events' in outdata and config['verbose']:
                    event_array = outdata['Events']
                    for event in event_array:
                        my_logger.info("EventType is ", event['EventType'])
                        my_logger.info("MessageId is ", event['MessageId'])
                        if 'EventId' in event:
                            my_logger.info("EventId is ", event['EventId'])
                        if 'EventTimestamp' in event:
                            my_logger.info("EventTimestamp is ", event['EventTimestamp'])
                        if 'Severity' in event:
                            my_logger.info("Severity is ", event['Severity'])
                        if 'Message' in event:
                            my_logger.info("Message is ", event['Message'])
                        if 'MessageArgs' in event:
                            my_logger.info("MessageArgs is ", event['MessageArgs'])
                        if 'Context' in outdata:
                            my_logger.info("Context is ", outdata['Context'])
                        my_logger.info("\n")
                if 'MetricValues' in outdata and config['verbose']:
                    metric_array = outdata['MetricValues']
                    my_logger.info("Metric Report Name is: ", outdata.get('Name'))
                    for metric in metric_array:
                        my_logger.info("Member ID is: ", metric.get('MetricId'))
                        my_logger.info("Metric Value is: ", metric.get('MetricValue'))
                        my_logger.info("TimeStamp is: ", metric.get('Timestamp'))
                        if 'MetricProperty' in metric:
                            my_logger.info("Metric Property is: ", metric['MetricProperty'])
                        my_logger.info("\n")

                ### Check the context and send the status OK if context matches
                if outdata.get('Context', None) != ContextDetail:
                    my_logger.info("Context ({}) does not match with the server ({})."
                          .format(outdata.get('Context', None), ContextDetail))
                StatusCode = """HTTP/1.1 200 OK\r\n\r\n"""
                connstreamout.send(bytes(StatusCode, 'UTF-8'))
                with open(logfile, 'a') as f:
                    if 'EventTimestamp' in outdata:
                        receTime = datetime.now()
                        sentTime = datetime.strptime(outdata['EventTimestamp'], "%Y-%m-%d %H:%M:%S.%f")
                        f.write("%s    %s    %sms\n" % (
                            sentTime.strftime("%Y-%m-%d %H:%M:%S.%f"), receTime, (receTime - sentTime).microseconds / 1000))
                    else:
                        f.write('No available timestamp.')

                try:
                    if event_count.get(str(fromaddr[0])):
                        event_count[str(fromaddr[0])] = event_count[str(fromaddr[0])] + 1
                    else:
                        event_count[str(fromaddr[0])] = 1

                    my_logger.info("Event Counter for Host %s = %s" % (str(fromaddr[0]), event_count[fromaddr[0]]))
                    my_logger.info("\n")
                    fd = open(outputfile, "a")
                    fd.write("Time:%s Count:%s\nHost IP:%s\nEvent Details:%s\n" % (
                        datetime.now(), event_count[str(fromaddr[0])], str(fromaddr), json.dumps(outdata)))
                    fd.close()
                except Exception as err:
                    my_logger.info(traceback.print_exc())

            if p.method() == 'GET':
                # for x in data_buffer:
                #     my_logger.info(x)
                res = "HTTP/1.1 200 OK\n" \
                      "Content-Type: application/json\n" \
                      "\n" + json.dumps(data_buffer)
                connstreamout.send(res.encode())
                data_buffer.clear()


        except Exception as err:
            outdata = connstreamout.read()
            my_logger.info("Data needs to read in normal Text format.")
            my_logger.info(outdata)

    finally:
        connstreamout.shutdown(socket.SHUT_RDWR)
        connstreamout.close()

import argparse

if __name__ == '__main__':
    """
    Main program
    """

    ### Print the tool banner
    logging.info('Redfish Event Listener v{}'.format(tool_version))

    argget = argparse.ArgumentParser(description='Redfish Event Listener (v{}) is a tool that deploys an HTTP(S) server to read and record events from Redfish services.'.format(tool_version))

    # config
    argget.add_argument('-c', '--config', type=str, default='./config.ini', help='Specifies the location of our configuration file (default: ./config.ini)')
    argget.add_argument('-v', '--verbose', action='count', default=0, help='Verbosity of tool in stdout')
    args = argget.parse_args()

    ### Initializing the global parameter
    from configparser import ConfigParser
    parsed_config = ConfigParser()
    parsed_config.read(args.config)

    def parse_list(string: str):
        if re.fullmatch(r'\[\]|\[.*\]', string):
            string = string.strip('[]')
        return [x.strip("'\"").strip() for x in string.split(',')]

    config['listenerip'] = parsed_config.get('SystemInformation', 'ListenerIP')
    config['listenerport'] = parsed_config.getint('SystemInformation', 'ListenerPort')
    config['usessl'] = parsed_config.getboolean('SystemInformation', 'UseSSL')

    config['certfile'] = parsed_config.get('CertificateDetails', 'certfile')
    config['keyfile'] = parsed_config.get('CertificateDetails', 'keyfile')

    config['destination'] = parsed_config.get('SubsciptionDetails', 'Destination')
    config['contextdetail'] = parsed_config.get('SubsciptionDetails', 'Context')
    config['protocol'] = parsed_config.get('SubsciptionDetails', 'Protocol')
    config['subscriptionURI'] = parsed_config.get('SubsciptionDetails', 'SubscriptionURI')
    config['eventtypes'] = parse_list(parsed_config.get('SubsciptionDetails', 'EventTypes'))

    config['serverIPs'] = parse_list(parsed_config.get('ServerInformation', 'ServerIPs'))
    config['usernames'] = parse_list(parsed_config.get('ServerInformation', 'UserNames'))
    config['passwords'] = parse_list(parsed_config.get('ServerInformation', 'Passwords'))
    config['logintype'] = parse_list(parsed_config.get('ServerInformation', 'LoginType'))

    config['certcheck'] = parsed_config.getboolean('ServerInformation', 'certcheck')
    config['verbose'] = args.verbose

    ### Perform the Subscription if provided
    SubscriptionURI, Protocol, ContextDetail, EventTypes, Destination = config['subscriptionURI'], config['protocol'], config['contextdetail'], config['eventtypes'], config['destination']

    target_contexts = []

    if not (len(config['serverIPs']) == len(config['usernames']) == len(config['passwords'])):
        my_logger.info("Number of ServerIPs does not match UserNames and Passwords")
    elif len(config['serverIPs']) == 0:
        my_logger.info("No subscriptions are specified. Continuing with Listener.")
    else:
        for dest, user, passwd, logintype in zip(config['serverIPs'], config['usernames'], config['passwords'], config['logintype']):
            try:
                ### Create Subsciption on the servers provided by users if any
                my_logger.info("ServerIP:: {}".format(dest))
                my_logger.info("UserName:: {}".format(user))
                my_ctx = redfish_client(dest, user, passwd, timeout=30)
                my_ctx.login(auth={
                    "Basic": AuthMethod.BASIC,
                    "Session": AuthMethod.SESSION,
                    "None": None
                }[logintype])
                response = event_service.create_event_subscription(my_ctx, config['destination'], client_context=config['contextdetail'], event_types=config['eventtypes'])
                if response.status in [200 + x for x in [0, 1, 2, 3, 4]]:
                    my_logger.info("Subcription is successful for %s" % dest)
                else:
                    my_logger.info("Subcription is not successful for %s or it is already present." % dest)
                target_contexts.append(my_ctx)
            except Exception as e:
                my_logger.info('Issue creating our ctx')
                my_logger.info(traceback.print_exc())
        my_logger.info("Continuing with Listener.")

    ### Accept the TCP connection using certificate validation using Socket wrapper
    useSSL = config['usessl']
    if useSSL:
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(certfile=config['certfile'], keyfile=config['keyfile'])

    # exit gracefully on CTRL-C
    import signal
    signal.signal(signal.SIGINT, lambda: sys.exit(0))

    ### Bind socket connection and listen on the specified port
    bindsocket = socket.socket()
    bindsocket.bind((config['listenerip'], config['listenerport']))
    bindsocket.listen(5)
    my_logger.info('Listening on {}:{} via {}'.format(config['listenerip'], config['listenerport'], 'HTTPS' if useSSL else 'HTTP'))
    event_count = {}
    data_buffer = []

    while True:
        try:
            ### Socket Binding
            newsocketconn, fromaddr = bindsocket.accept()
            try:
                ### Multiple Threads to handle different request from different servers
                threading.Thread(target=process_data, args=(newsocketconn, fromaddr)).start()
            except Exception as err:
                my_logger.info(traceback.print_exc())
        except Exception as err:
            my_logger.info("Exception occurred in socket binding.")
            my_logger.info(traceback.print_exc())
