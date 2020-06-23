from TCPServerClient import *
import socket
import json
import paramiko
import re
from multiprocessing import Process
import sys
import subprocess
from Requests import Request, Response, PingRequest, PingResponse
from threading import Thread

MESSAGE_SIZE = 20
HOMECONTROLLER_ITERATION_TIME = 0.5
HOME_CONTROLLER_PING_RATE = 10
TMP = '/tmp'
DEFINITIONS_FILE = os.getenv('DEFINITIONS_FILE', '/home/maxime/PycharmProjects/HomeController/Definitions.xml')
LOCAL_HOST = '127.0.0.1'
INACTIVITY_TIMEOUT = 4


class HomeController:
    def __init__(self):
        self.processes = {}
        self.environment_variables = {}
        self.remote_environment_variables = {}
        self.linking_request_numbers = []
        self.ping_thread = None
        self.ping = True
        self.queue_io = QueueIO()
        self.routing = {}
        self.next_process_id = 2
        # self.request_definitions = RequestDefinitions()
        # self.read_definitions()
        # self.start_processes()

    def get_process_by_id(self, process_id):
        for process_name, process in self.processes.items():
            if process.member_id == process_id:
                return process
        return None

    @staticmethod
    def link_queues(request, receiver, sender):
        # receiver is the receiver of data in this link, so the sender of the original request
        response_found = False
        last_alive_time = datetime.datetime.now()
        timed_out = False
        while not response_found and not timed_out:
            try:
                message_data = sender.queue_io.input_queue.get(timeout=0.5)
                Logger('HomeController.link_queues received data {}'.format(message_data), 'D')
                if message_data[ENCODED_MESSAGE_INDENTIFIER_INDEX] == REQUEST_IDENT:
                    message = Request(encoded_data=message_data)
                else:
                    message = Response(encoded_data=message_data)
                if message.number == request.number:
                    last_alive_time = datetime.datetime.now()
                    if type(message) is Response:
                        response_found = True
                        Logger('HomeController.link_queues got expected response {} number {} with hop {}'
                               .format(message.what, message.number, message.hop), 'D')
                        Logger('HomeController.link_queues removing request number {} from sender and receiver '
                               'queue_io piping_number lists'.format(request.number), 'D')
                        receiver.queue_io.piping_numbers.remove(request.number)
                        sender.queue_io.piping_numbers.remove(request.number)
                    Logger('HomeController.link_queues putting message data in output_queue: {}'
                           .format(message.encode()), 'D')
                    receiver.queue_io.output_queue.put(message.encode())
                    Logger('HomeController.link_queues successfully put data in output_queue', 'D')
                else:
                    Logger('HomeController.link_queues received unmatched response {} number {} hop {}. '
                           'Putting back data in input queue'.format(message.what, message.number, message.hop), 'D')
                    sender.queue_io.input_queue.put(message_data)
                    time.sleep(0.5)
                timed_out = (datetime.datetime.now() - last_alive_time).total_seconds() > INACTIVITY_TIMEOUT \
                    and INACTIVITY_TIMEOUT
            except Empty:
                time.sleep(0.5)
        if timed_out:
            Logger('HomeController.link_queues timed out because of inactivity waiting for data request number {}. '
                   'Timeout is {}'.format(request.number, INACTIVITY_TIMEOUT), 'E')
            response = Response(message=request)
            response.identifier = ErrorCodes.INACTIVITY_TIMEOUT_ERROR
            receiver.queue_io.output_queue.put(response.encode())
            Logger('HomeController.link_queues removing request number {} from sender and receiver '
                   'queue_io piping_number lists'.format(request.number), 'D')
            receiver.queue_io.piping_numbers.remove(request.number)
            sender.queue_io.piping_numbers.remove(request.number)

    def handle_request(self, request, sender, receiver):
        Logger('HomeController.handle_request handling request {} number {} hop {}. Sender is {}, receiver is {}'
               .format(request.what, request.number, request.hop, sender.name, receiver.name), 'D')
        request.add_hop()
        # self.linking_request_numbers.append(request.number)
        Logger('HomeController.handle_request adding request number {} to self.linking_request_numbers. List is {}'
               .format(request.number, self.linking_request_numbers), 'D')
        Logger('HomeController.handle_request is adding request number {} to sender and receiver queue_io '
               'piping_numbers'.format(request.number), 'D')
        sender.queue_io.piping_numbers.append(request.number)
        receiver.queue_io.piping_numbers.append(request.number)
        Logger('HomeController.handle_request is sending data : {}'.format(request.encode()), 'D')
        sender.queue_io.output_queue.put(request.encode())
        receiver.queue_io.output_queue.put(request.encode())
        self.link_queues(request, sender, receiver)

    def preprocess_request(self, request):
        response = None
        if request.what == 'process_statuses':
            response = self.handle_process_statuses(request)
        return response

    def handle_process_statuses(self, request):
        response = Response(message=request)
        error_message = ''
        for process_name, process in self.processes.items():
            if process.error_code != ErrorCodes.NO_ERROR:
                error_message += 'Process {} is in error state,'.format(process_name)
        response.set_data(error_message)
        Logger('HomeController.get_input_messages got process_statuses request. Returning data to '
               'queue: {}'.format(response.encode()), 'D')
        return response

    @staticmethod
    def handle_response(response, process):
        if response.what == 'ping':
            process.error_code = response.identifier

    def get_input_messages(self):
        Logger('HomeController.get_input_messages starting', 'D')
        while True:
            # message = self.queue_io.get_input_message()
            # if not message:
            #     break
            # else:
            try:
                message_data = self.queue_io.input_queue.get(timeout=0.5)
                if message_data[ENCODED_MESSAGE_INDENTIFIER_INDEX] == REQUEST_IDENT:
                    message = Request(encoded_data=message_data)
                else:
                    message = Response(encoded_data=message_data)
                Logger('HomeController.get_input_messages got message: {}'.format(message), 'D')
                if message.number in self.routing:
                    Logger('HomeController.get_input_messages message is in routing numbers', 'D')
                    # Message is being routed. Send message to target queue and remove from
                    # routing if message is a response
                    if not isinstance(self.routing[message.number], self.HomeControllerProcess):
                        send_message(self.routing[message.number], message)
                    elif message.sender_id == 1 and isinstance(message, Response):
                        Logger('HomeController.get_input_messages received response: {}'.format(message), 'D')
                        self.handle_response(message, self.routing[message.number])
                    if isinstance(message, Response):
                        del self.routing[message.number]
                else:
                    response = self.preprocess_request(message)
                    if response:
                        Logger('HomeController.get_input_messages got response from preprocess_request: {}'
                               .format(response), 'D')
                        sender_process = self.get_process_by_id(message.sender_id)
                        if not sender_process:
                            Logger('HomeController.get_input_messages received message with invalid sender_id: {}'
                                   .format(message), 'E')
                        Logger('HomeController.get_input_messages sender process is {}'
                               .format(sender_process.name), 'D')
                        sender_process.queue_io.output_queue.put(response.encode())
                        Logger('HomeController.get_input_messages successfully sent back response', 'D')
                    else:
                        # Message is not yet being routed. Fing the message destination
                        message.add_hop()
                        Logger('HomeController.get_input_messages is not yet routing message', 'D')
                        sender_process = self.get_process_by_id(message.sender_id)
                        sender_process.queue_io.output_queue.put(message.encode())
                        for process_name, process in self.processes.items():
                            if process.queue_io.request_definitions.get(message.what) and \
                                    process is not sender_process and not process.remote:
                                Logger('HomeController.get_input_messages will route message {} from process {} '
                                       'to target process {}'
                                       .format(message, sender_process, process.name), 'D')
                                Logger('HomeController.get_input_messages forwarding message to process {} input_queue'
                                       .format(process.name), 'D')
                                process.queue_io.output_queue.put(message.encode())
                                self.routing[message.number] = sender_process.queue_io.output_queue
                                break
            except Empty:
                break

        # for _, sender_process in self.processes.items():
        #     queue_request = sender_process.get_message()
        #     while queue_request:
        #         Logger('HomeControllerProcess.get_input_message received queue request {} number {} with hop {}'
        #                .format(queue_request.what, queue_request.number, queue_request.hop), 'D')
        #         if queue_request.what == 'process_statuses':
        #             response = self.handle_process_statuses(queue_request)
        #             sender_process.queue_io.output_queue.put(response.encode())
        #         else:
        #             # Find the process with the matching request definition
        #             for process_name, receiver_process in self.processes.items():
        #                 if receiver_process.queue_io.request_definitions.get(queue_request.what) and \
        #                         receiver_process is not sender_process and not receiver_process.remote:
        #                     Logger('HomeController.handle_request will forward request {} number {} '
        #                            'to process {} after sending back request with added hop number'
        #                            .format(queue_request.what, queue_request.number, process_name), 'D')
        #                     handle_request_thread = Thread(target=self.handle_request, args=(queue_request,
        #                                                                                      sender_process,
        #                                                                                      receiver_process))
        #                     handle_request_thread.start()
        #                     break
        #         # process.queue_io.send_response(self.handle_request(queue_request, process))
        #         queue_request = sender_process.get_message()
        Logger('HomeController.get_input_messages end of function', 'D')

    def add_request_definition(self, **kwargs):
        self.request_definitions.set(**kwargs)

    def start_processes(self):
        processes = list(self.processes.values())
        while processes:
            process = processes.pop()
            if not process.run_after or self.processes[process.run_after].started:
                process.start()
            elif process.run_after and \
                    self.processes[process.run_after].error_code == ErrorCodes.HOST_UNREACHABLE_ERROR:
                process.error_code = ErrorCodes.HOST_UNREACHABLE_ERROR
            else:
                processes.insert(0, process)

    def stop_processes(self):
        Logger('Stopping processes', 'D')
        for process_name, process in self.processes.items():
            if process.process and not process.remote:
                Logger('Attempting to terminate process {} with pid {}'.format(process_name, process.process.pid), 'D')
                process.stop()

    def ping_processes(self):
        Logger('HomeController.ping_processes started', 'D')
        while self.ping:
            for process_name, process in self.processes.items():
                if process.pingable and process.error_code != ErrorCodes.HOST_UNREACHABLE_ERROR:
                    try:
                        # process.error_code = process.ping()
                        ping_request = PingRequest(sender_id=1)
                        self.routing[ping_request.number] = process
                        process.queue_io.output_queue.put(ping_request.encode())
                        # if process.error_code == 0:
                        #     print('Process {} OK'.format(process_name))
                    except TCPException as e:
                        process.error_code = e.error_code
                else:
                    print('Process {} is in error state'.format(process_name))
                    # self.get_input_messages()
            time.sleep(HOME_CONTROLLER_PING_RATE)

    def run(self):
        self.ping_thread = Thread(target=self.ping_processes)
        self.ping_thread.start()
        try:
            while True:
                Logger('HomeController.run starting iteration', 'D')
                self.get_input_messages()
                time.sleep(HOMECONTROLLER_ITERATION_TIME)
        except KeyboardInterrupt as e:
            Logger('HomeController received KeyboardInterrupt :\n{}'.format(e), 'D')
            self.ping = False
            if self.ping_thread:
                self.ping_thread.join()
            self.stop_processes()

    class HomeControllerProcess:
        def __init__(self, request_definitions=None, input_queue=None, output_queue=None, member_id=0, **kwargs):
            self.remote = kwargs.pop('Remote', 'false').lower() == 'true'
            self.address = kwargs.pop('Address', None)
            self.command = kwargs.pop('Command', None)
            self.ping_number = 0
            self.error_code = 0
            self.environment_variables = {}
            self.app_name = None
            self.process = None
            self.base_dir = None
            base_dir = kwargs.pop('BaseDir', None)
            # Replace environment variables in base_dir
            if self.base_dir:
                self.set_base_dir(base_dir)
            self.run_after = kwargs.pop('RunAfter', None)
            self.started = False
            self.run_as_service = kwargs.pop('RunAsService', 'false').lower() == 'true'
            self.environment_file = kwargs.pop('EnvironmentFile', None)
            self.module = kwargs.pop('PythonModule', None)
            self.class_call = kwargs.pop('PythonClass', None)
            self.method_call = kwargs.pop('PythonClassMethod', None)
            self.server_ip_addr = kwargs.pop('ServerIPAddress', None)
            self.name = kwargs.pop('Name')
            self.local_server = kwargs.pop('LocalServer', 'false').lower() == 'true'
            self.pingable = kwargs.pop('Pingable', 'true').lower() == 'true'
            self.queue_io = QueueIO(input_queue=input_queue, output_queue=output_queue)
            self.member_id = member_id
            if request_definitions:
                self.queue_io.set_all_definitions(request_definitions)

        def resolve_environment_variables(self):
            while True:
                all_resolved = True
                for name, value in self.environment_variables.items():
                    match = re.search(r'\$([A-Za-z0-9_]+)', value)
                    if match and match.groups() and match.group(1):
                        matched = match.group(1)
                        all_resolved = False
                        if matched in self.environment_variables:
                            while '${}'.format(matched) in value:
                                value = value.replace('${}'.format(matched), self.environment_variables[matched])
                            self.environment_variables[name] = value
                if all_resolved:
                    break

        def set_base_dir(self, base_dir):
            match = re.search(r'(\$[A-Za-z-0-9_]+)', base_dir)
            if match and match.group(1):
                if match.group(1)[1:] in self.environment_variables:
                    env_val = self.environment_variables[match.group(1)[1:]]
                else:
                    env_val = os.getenv(match.group(1))
                if not env_val:
                    # Manage error
                    pass
                else:
                    self.base_dir = base_dir.replace(match.group(1), env_val)

        def get_message(self):
            Logger('HomeControllerProcess.get_messages process name {} calling queue_io.get_request'
                   .format(self.name), 'D')
            return self.queue_io.get_input_message()

        def ping(self):
            Logger('HomeControllerProcess.ping will ping process {}'.format(self.name), 'D')
            try:
                if self.remote:
                    tcp_client = TCPClient(self.address)
                    ping_response = tcp_client.ping_server()
                    # tcp_client.connect(max_attempt=max_attempt)
                    # ping_response = tcp_client.get_response(tcp_request)
                    # tcp_client.disconnect()
                else:
                    ping_request = PingRequest()
                    ping_response = self.queue_io.send_request(ping_request)
                self.ping_number += 1
            except RequestException as e:
                return e.error_code
            return ping_response.error_code

        def stop(self):
            if self.process:
                self.process.terminate()
                Logger('Process {} with pid {} terminated successfully'.format(self.name, self.process.pid), 'D')
            self.queue_io.stop()

        def get_state(self):
            if self.remote:
                tcp_client = TCPClient(ip_addr=self.address)
                response = tcp_client.get_server_state()
            else:
                get_state_request = Request(what='get_state', message_type='query', number=0)
                self.queue_io.output_queue.put(get_state_request.encode())
                response = self.queue_io.expect_response(get_state_request)
            return response.get_payload_data()

        def start(self):
            # Replace any environment variables in the command
            regex = r'\$([a-zA-Z0-9_]+)'
            while self.command and re.search(regex, self.command):
                match = re.search(regex, self.command)
                if match.group(1) in self.environment_variables:
                    self.command = self.command.replace('${}'.format(match.group(1)),
                                                        self.environment_variables[match.group(1)])
                else:
                    # TODO: manage error
                    pass
            if self.remote:
                # Check if server is already running
                tcp_client = TCPClient(ip_addr=self.address)
                try:
                    server_state = tcp_client.get_server_state().get_payload_data()
                except TCPException:
                    ssh = paramiko.SSHClient()
                    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    ssh.load_system_host_keys()
                    ssh.connect(self.address, username='pi', password='Batman89')
                    if self.run_as_service:
                        # Write environment file
                        with open(os.path.join(TMP, self.environment_file), 'w') as env_file:
                            env_file.writelines(['{}={}\n'
                                                .format(name, value) for
                                                 name, value in self.environment_variables.items()])
                        ftp_client = ssh.open_sftp()
                        ftp_client.put(os.path.join(TMP, self.environment_file),
                                       os.path.join(self.base_dir, self.environment_file))
                    # Go to base directory
                    if self.base_dir:
                        command = 'cd {}; {}'.format(self.base_dir, self.command)
                        # i, o, e = ssh.exec_command('cd {}'.format(self.base_dir))
                        # print(o.read())
                        # print(e.read())
                    else:
                        command = self.command
                    ssh.exec_command(command, environment=self.environment_variables)
                    # print(o.read())
                    # print(e.read())
                    ssh.close()
                    time.sleep(1)
                    server_state = tcp_client.get_server_state().get_payload_data()
                except OSError:
                    self.error_code = ErrorCodes.HOST_UNREACHABLE_ERROR
                    return
                if server_state == 'PENDING_DEFINITIONS_STATE':
                    self.send_definitions()
                elif server_state not in ['CONNECTED_STATE', 'PENDING_CONNECTION_STATE']:
                    raise TCPException('Server at address {} is in state {}'.format(self.address, server_state))
            else:
                # Set environment variables
                tmp_env_var = dict(os.environ)
                os.environ.update(self.environment_variables)
                if self.base_dir:
                    os.chdir(self.base_dir)
                if self.module and self.class_call and self.method_call:
                    # Add the project base directory to system path
                    sys.path.append(self.base_dir)
                    # Import the python module
                    try:
                        exec('from {} import {}'.format(self.module, self.class_call))
                        # Create queues to pass to process
                        def_file = DEFINITIONS_FILE
                        obj = eval(self.class_call)(ip_addr=self.server_ip_addr,
                                                    def_file=def_file,
                                                    input_queue=self.queue_io.output_queue,
                                                    output_queue=self.queue_io.input_queue,
                                                    app_name=self.app_name,
                                                    member_id=self.member_id)
                        obj.read_definitions(DEFINITIONS_FILE, self.app_name)
                        call_method = getattr(obj, self.method_call)
                        self.process = Process(target=call_method)
                        self.process.start()
                    except ModuleNotFoundError:
                        # Manage error
                        pass
                elif self.command:
                    process = subprocess.Popen(self.command.split(','))
                    self.process = process
                # Put back original environment
                os.environ.update(tmp_env_var)
            self.started = True

        def get_definitions_dict(self):
            return self.queue_io.request_definitions.as_dict()

        def send_definitions(self):
            definitions = self.get_definitions_dict()
            definitions = json.dumps(definitions).encode('utf-8')
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.address, SERVER_PORT))
            # Send initial request
            init_request = TCPRequest(what='accept_definitions', message_type='command', data_type='int')
            s.sendall(init_request.encode())
            # Wait for initial request response
            init_response = TCPResponse(encoded_data=s.recv(1024))
            if init_response.error_code == TCP_RESPONSE_NO_ERROR:
                # server ready to receive definitions
                while definitions:
                    if len(definitions) > MESSAGE_SIZE:
                        partial_message = definitions[:MESSAGE_SIZE - 1]
                        definitions = definitions[MESSAGE_SIZE - 1:]
                    else:
                        partial_message = definitions
                        definitions = b''
                    s.send(len(partial_message).to_bytes(TCP_MESSAGE_SIZE_LENGTH, byteorder='big') + partial_message)
                s.send(b'')
            s.close()

    def read_definitions(self):
        root = ElementTree.parse(DEFINITIONS_FILE).getroot()
        # Read HomeController RequestDefinitions
        if root.find('RequestDefinitions'):
            request_definitions = root.find('RequestDefinitions').findall('RequestDefinition')
            for request_definition in request_definitions:
                self.add_request_definition(**request_definition.attrib)
        # Read environment variables
        env_var_definitions = root.find('EnvironmentVariables')
        for host in env_var_definitions:
            if host.get('Address') == LOCAL_HOST:
                for env_var_def in host.findall('EnvironmentVariable'):
                    self.environment_variables[env_var_def.get('Name')] = env_var_def.text
            else:
                if host.get('Address') not in self.remote_environment_variables:
                    self.remote_environment_variables[host.get('Address')] = {}
                for env_var_def in host.findall('EnvironmentVariable'):
                    self.remote_environment_variables[host.get('Address')][env_var_def.get('Name')] = env_var_def.text
        app_definitions = root.find('AppDefinitions')
        for app_definition in app_definitions.findall('AppDefinition'):
            app_base_dir = app_definition.get('BaseDir')
            app_name = app_definition.get('AppName')
            # Read the request definitions
            request_definitions = {}
            if app_definition.find('RequestDefinitions'):
                for request_definition in app_definition.find('RequestDefinitions').findall('RequestDefinition'):
                    request_definitions[request_definition.get('Name')] = request_definition.attrib
            for process_definition in app_definition.findall('HomeControllerProcess'):
                process_name = process_definition.get('Name')
                process = self.HomeControllerProcess(**process_definition.attrib,
                                                     input_queue=self.queue_io.input_queue,
                                                     request_definitions=request_definitions,
                                                     member_id=self.next_process_id)
                self.next_process_id += 1
                # Assign global environment variables
                process.environment_variables = dict(self.environment_variables)
                # Read process-specific environment variables
                for env_var_def in process_definition.findall('EnvironmentVariable'):
                    process.environment_variables[env_var_def.get('Name')] = env_var_def.text
                if process.address in self.remote_environment_variables:
                    process.environment_variables.update(self.remote_environment_variables[process.address])
                process.resolve_environment_variables()
                if not process.base_dir and app_base_dir:
                    process.set_base_dir(app_base_dir)
                process.app_name = app_name
                self.processes[process_name] = process


if __name__ == '__main__':
    home_controller = HomeController()
    home_controller.read_definitions()
    home_controller.start_processes()
    home_controller.run()
