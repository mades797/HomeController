from unittest import mock, TestCase
from HomeController import HomeController
from TCPServerClient import *
from TCPInterface import TCPInterfaceServer
from Requests import RequestDefinitions
import TCPServerClient as TcpServerClientPkg


class HomeControllerTestCase(TestCase):

    def setUp(self):
        self.processes = []

    def tearDown(self):
        for process_pid in self.processes:
            os.kill(process_pid, signal.SIGTERM)
        time.sleep(1)
        print('tearDown done')

    # This test simply starts a TCPClient that does not connect to a server and not queue interface
    def test_tcp_client_run(self):
        print('start of test_tcp_client_run')
        """
        Test conditions: TCPClient.run method will run 10 times before a KeyboardInterrupt will be simulated
        Expected:
            TCPClient.connect called 10 times
            TCPClient.process_intput_queue to be called 10 times
            TCPClient.do to be called 10 times
            TCPClient.disconnect to be called once
        """
        tcp_client = TCPClient()
        tcp_client.rate = 0
        tcp_client.do_rate = 0
        tcp_client.connect = mock.MagicMock()
        tcp_client.process_input_queue = mock.MagicMock()
        tcp_client.do = mock.MagicMock()
        tcp_client.disconnect = mock.MagicMock()
        iteration_number = 0
        max_iteration_number = 10

        def connect_side_effect(**_):
            nonlocal iteration_number, max_iteration_number
            iteration_number += 1
            if iteration_number > max_iteration_number:
                raise KeyboardInterrupt
        tcp_client.connect.side_effect = connect_side_effect
        tcp_client.run()
        # Assertions
        tcp_client.connect.assert_has_calls([mock.call(max_attempt=1) for _ in range(0, max_iteration_number)])
        tcp_client.process_input_queue.assert_has_calls([mock.call() for _ in range(0, max_iteration_number)])
        tcp_client.do.assert_has_calls([mock.call() for _ in range(0, max_iteration_number)])
        tcp_client.disconnect.assert_called_once()
        self.assertTrue(True)
        print('test_tcp_client_run done')

    # This test simply starts a TCPClient that does not connect to a server and not queue interface

    @mock.patch('TCPServerClient.TCPRequest')
    @mock.patch('TCPServerClient.Response')
    @mock.patch('TCPServerClient.SocketWrapper')
    def test_tcp_client_runtime_connect(self, mock_socket, mock_response, mock_tcprequest):
        print('start of test_tcp_client_runtime_connect')
        """
        Test conditions:
            TCPClient.run method will run 15 times before a KeyboardInterrupt will be simulated. The server will
            accept the connection at iteration 8 and respond get_state requests with 'ERROR_STATE'
            for 5 iterations. The client will successfully connect at iteration 12
        Expected:
            TCPClient.process_intput_queue to be called 15 times
            TCPClient.do to be called 15 times
            TCPClient.disconnect to be called once
            TCPClient.start_receiver_process to be called 5 times
        """
        tcp_client = TCPClient(ip_addr='ip_addr')
        connect_response = Response(what='connect', message_type='command', data_type='int')
        connect_response.identifier = ErrorCodes.NO_ERROR
        connect_response.set_data(ErrorCodes.COMMAND_SUCCESS)
        mock_response.return_value = connect_response
        # tcp_client.command = mock.MagicMock(return_value=connect_response)
        tcp_client.rate = 0
        tcp_client.do_rate = 0
        tcp_client.process_input_queue = mock.MagicMock()
        tcp_client.do = mock.MagicMock()
        # tcp_client.disconnect = mock.MagicMock()
        tcp_client.start_receiver_process = mock.MagicMock()
        iteration_number = 0
        get_state_number = 0
        get_state_success_number = 5
        max_iteration_number = 15
        connection_iteration = 8
        fake_get_state_response = mock.MagicMock()
        tcp_client.get_server_state = mock.MagicMock(return_value=fake_get_state_response)

        def get_payload_side_effect():
            nonlocal get_state_number, get_state_success_number
            get_state_number += 1
            if get_state_number >= get_state_success_number:
                return 'READY_STATE'
            else:
                return 'ERROR_STATE'

        def do_side_effect(**_):
            nonlocal iteration_number, max_iteration_number
            iteration_number += 1
            if iteration_number > max_iteration_number:
                raise KeyboardInterrupt

        def connect_side_effect(*_):
            nonlocal iteration_number, max_iteration_number
            if iteration_number < connection_iteration:
                raise ConnectionRefusedError
        tcp_client.do.side_effect = do_side_effect
        mock_socket.return_value.connect.side_effect = connect_side_effect
        fake_get_state_response.get_payload_data.side_effect = get_payload_side_effect

        tcp_client.run()
        # Assertions
        tcp_client.process_input_queue.assert_has_calls([mock.call() for _ in range(0, max_iteration_number)])
        # tcp_client.command.assert_called_once_with('connect')
        mock_tcprequest.assert_called_once_with(what='connect', message_type='command', data_type='int')
        mock_socket.return_value.send.assert_called_once_with(mock_tcprequest.return_value.encode.return_value)
        tcp_client.do.assert_has_calls([mock.call() for _ in range(0, max_iteration_number)])
        tcp_client.start_receiver_process.assert_called_once()
        mock_socket.return_value.finish \
            .assert_has_calls([mock.call() for _ in range(get_state_success_number)])
        self.assertFalse(tcp_client.connected)
        print('test_tcp_client_runtime_connect done')

    def test_tcp_client_ping_get_state(self):
        print('start of test_tcp_client_ping_get_state')
        """
        Test conditions:
            TCPClient.run to be called in seperate process. The client will receive a get_state request, will
            be pinged 50 times and finally receive another get_state_request
        Expected:
            1. The client will respond to the get_state request with an error code of NO_SERVER_DEFINED_ERROR
            and a state of ERROR_STATE
            2. The client will response with the right response number each time
            3. The client will respond to the get_state request with an error code of NO_SERVER_DEFINED_ERROR
        """
        input_queue = Queue()
        output_queue = Queue()
        tcp_client = TCPClient(input_queue=input_queue, output_queue=output_queue)
        run_process = Process(target=tcp_client.run)
        run_process.start()
        # Assertions
        get_state_request = Request(what='get_state', message_type='query', data_type='str')
        input_queue.put(get_state_request.encode())
        response_data = output_queue.get()
        response = Response(encoded_data=response_data)
        response.data_type = 'str'
        self.assertEqual(response.number, get_state_request.number)
        self.assertEqual(response.identifier, ErrorCodes.NO_SERVER_DEFINED_ERROR)
        self.assertEqual(response.get_payload_data(), 'ERROR_STATE')
        for number in range(0, 50):
            ping_request = PingRequest()
            print('Sending ping request number {}'.format(number))
            input_queue.put(ping_request.encode())
            response_data = output_queue.get()
            response = Response(encoded_data=response_data)
            self.assertEqual(response.number, ping_request.number)
            self.assertEqual(response.identifier, ErrorCodes.NO_ERROR)
        get_state_request = Request(what='get_state', message_type='query', data_type='str')
        input_queue.put(get_state_request.encode())
        response_data = output_queue.get()
        response = Response(encoded_data=response_data)
        response.data_type = 'str'
        self.assertEqual(response.number, get_state_request.number)
        self.assertEqual(response.identifier, ErrorCodes.NO_SERVER_DEFINED_ERROR)
        self.assertEqual(response.get_payload_data(), 'ERROR_STATE')
        run_process.terminate()
        print('test_tcp_client_ping_get_state done')

    def test_tcp_client_get_state(self):
        print('start of test_tcp_client_get_state')
        """
        Test conditions: The client is started without a server. After 5 seconds, a server accepts the
                         client's connection.
        Expected: Before the server is started, the client receives get_state requests and responds with
                  READY_STATE. After the sevrer is started, the client connects and response
                  READY_STATE to the get_state requests
        """
        input_queue = Queue()
        output_queue = Queue()
        tcp_client = TCPClient(ip_addr='127.0.0.1', input_queue=input_queue, output_queue=output_queue)
        # tcp_client.start_receiver_process = mock.MagicMock()
        tcp_server = TCPServer(ip_addr='127.0.0.1')
        iteration_time = 1  # seconds
        iteration_number = 5
        client_process = Process(target=tcp_client.run)
        server_process = Process(target=tcp_server.run)
        client_process.start()
        self.processes.append(client_process.pid)
        for i in range(0, iteration_number):
            get_state_request = Request(what='get_state', message_type='query', data_type='str')
            input_queue.put(get_state_request.encode())
            response_data = output_queue.get()
            response = Response(encoded_data=response_data)
            response.data_type = 'str'
            self.assertEqual(response.number, get_state_request.number)
            self.assertEqual(response.get_payload_data(), 'READY_STATE')
            self.assertEqual(response.identifier, ErrorCodes.NO_ERROR)
            time.sleep(iteration_time)
        server_process.start()
        self.processes.append(server_process.pid)
        time.sleep(1)
        # send definitions
        definitions = {'test_def': {'Name': 'test_def', 'DataType': 'str', 'NumberOfArguments': 0}}
        send_definitions('127.0.0.1', definitions)
        time.sleep(1)
        for i in range(0 + 10, iteration_number + 10):
            get_state_request = Request(what='get_state', message_type='query', data_type='str')
            input_queue.put(get_state_request.encode())
            response_data = output_queue.get()
            response = Response(encoded_data=response_data)
            response.data_type = 'str'
            self.assertEqual(response.number, get_state_request.number)
            self.assertEqual(response.get_payload_data(), 'READY_STATE')
            self.assertEqual(response.identifier, ErrorCodes.NO_ERROR)
            time.sleep(iteration_time)
        print('test_tcp_client_get_state done')

    def test_tcp_server_ping_get_state(self):
        print('start of test_tcp_server_ping_get_state')
        """
        Test Conditions:
            The server is started wihtout a client. The get_state query is sent through the queue. then 50 pings are
            sent through the queue. Finally another get_state query is sent throught the queue
        Expected:
            1. The server responds to the first get_state request with PENDING_DEFINITIONS_STATE
            2. The server responds to the ping requests with the proper response number
            3. The server responds to the last get_state request with PENDING_DEFINITIONS_STATE
        """
        input_queue = Queue()
        output_queue = Queue()
        tcp_server = TCPServer(input_queue=input_queue, output_queue=output_queue, ip_addr='127.0.0.1')
        run_process = Process(target=tcp_server.run)
        run_process.start()
        # Assertions
        get_state_request = Request(what='get_state', message_type='query', data_type='str')
        input_queue.put(get_state_request.encode())
        response_data = output_queue.get()
        response = Response(encoded_data=response_data)
        response.data_type = 'str'
        self.assertEqual(response.number, get_state_request.number)
        self.assertEqual(response.identifier, ErrorCodes.NO_ERROR)
        self.assertEqual(response.get_payload_data(), 'PENDING_DEFINITIONS_STATE')
        for number in range(0, 50):
            ping_request = PingRequest()
            print('Sending ping request number {}'.format(number))
            input_queue.put(ping_request.encode())
            response_data = output_queue.get()
            response = Response(encoded_data=response_data)
            self.assertEqual(response.number, ping_request.number)
            self.assertEqual(response.identifier, ErrorCodes.NO_ERROR)
        get_state_request = Request(what='get_state', message_type='query', data_type='str')
        input_queue.put(get_state_request.encode())
        response_data = output_queue.get()
        response = Response(encoded_data=response_data)
        response.data_type = 'str'
        self.assertEqual(response.number, get_state_request.number)
        self.assertEqual(response.identifier, ErrorCodes.NO_ERROR)
        self.assertEqual(response.get_payload_data(), 'PENDING_DEFINITIONS_STATE')
        run_process.terminate()
        print('test_tcp_server_ping_get_state done')

    def test_tcp_server_accept_definitions(self):
        print('start of test_tcp_server_accept_definitions')
        """
        Test conditions:
            1. The server is started
            2. The server is pinged through the socket
            3. The get_state query is sent
            4. The definitions are sent
            5. The server is pinged through the socket
            6. The get_state query is sent
        Expected:
            1. The client cannot connect to the server because the server did not receive request definitions
            2. The server responds with a error code of DEFINITIONS_NOT_RECEIVED_ERROR
            3. The server responds with an error code of DEFINITIONS_NOT_RECEIVED_ERROR and state of
               PENDING_DEFINITIONS_STATE
            5. The server responds to the ping with an error code of NO_ERROR
            6. The server responds with an error code of NO_ERROR and state of READY_STATE
        """
        tcp_server = TCPServer(ip_addr='127.0.0.1')
        server_process = Process(target=tcp_server.run)
        # 1. The server is started
        print('1. The server is started')
        server_process.start()
        time.sleep(1)
        tcp_client = TCPClient(ip_addr='127.0.0.1')
        with self.assertRaises(TCPException):
            try:
                tcp_client.connect(max_attempt=3)
            except TCPException as e:
                self.assertEqual(e.error_code, ErrorCodes.CLIENT_CONNECTION_ERROR)
                raise e
        # 2. The server is pinged through the socket
        print('2. The server is pinged through the socket')
        response = tcp_client.ping_server()
        self.assertEqual(response.identifier, ErrorCodes.DEFINITIONS_NOT_RECEIVED_ERROR)
        # 3. The get_state query is sent
        print('3. The get_state query is sent')
        response = tcp_client.get_server_state()
        self.assertEqual(response.identifier, ErrorCodes.DEFINITIONS_NOT_RECEIVED_ERROR)
        self.assertEqual(response.get_payload_data(), 'PENDING_DEFINITIONS_STATE')
        # 4. The definitions are sent
        print('# 4. The definitions are sent')
        definitions = {'test_def': {'Name': 'test_def', 'DataType': 'str', 'NumberOfArguments': 0}}
        send_definitions('127.0.0.1', definitions)
        # 5. The server is pinged through the socket
        print('# 5. The server is pinged through the socket')
        tcp_client.connect()
        ping_request = TCPRequest(message=PingRequest())
        response = tcp_client.get_response(ping_request)
        tcp_client.disconnect()
        self.assertEqual(response.identifier, ErrorCodes.NO_ERROR)
        # 6. The get_state query is sent
        print('# 6. The get_state query is sent')
        get_state_request = TCPRequest(what='get_state', message_type='query', data_type='str')
        tcp_client.connect()
        response = tcp_client.get_response(get_state_request)
        response.data_type = 'str'
        tcp_client.disconnect()
        self.assertEqual(response.number, get_state_request.number)
        self.assertEqual(response.identifier, ErrorCodes.NO_ERROR)
        self.assertEqual(response.get_payload_data(), 'READY_STATE')
        os.kill(server_process.pid, signal.SIGINT)
        print('test_tcp_server_accept_definitions done')

    def test_end_client_to_middle_server(self):
        print('start of test_end_client_to_middle_server')
        """
        Test conditions:
            A TCPClient sends requests to TCPInterface
        Expected:
            The TCPInterface receives the requests through the socket and forwards them to it's output queue. The
            test then puts the response in the middle_server input queue and the middle server forwards the response
            to the socket
        """
        middle_server = TCPInterfaceServer()
        middle_server.host_ipaddr = '127.0.0.1'
        # middle_server.queue_io.request_definitions.received_definitions = True
        output_queue = Queue()
        input_queue = Queue()
        middle_server.queue_io.output_queue = QueueWrapper(output_queue)
        middle_server.queue_io.input_queue = QueueWrapper(input_queue)
        middle_server_process = Process(target=middle_server.run)
        middle_server_process.start()
        self.processes.append(middle_server_process.pid)
        end_client = TCPClient(ip_addr='127.0.0.1')
        end_client.set_request_definitions({'test': {'Name': 'test', 'DataType': 'bool', 'NumberOfArguments': 0}})
        time.sleep(1)
        payload_data = False
        for i in range(0, 15):
            print('Attempt number {}'.format(i))
            end_client.connect()
            tcp_request_send = TCPRequest(what='test', message_type='query', data_type='bool')
            end_client.socket.send(tcp_request_send.encode())
            queue_data = output_queue.get()
            request_received = Request(encoded_data=queue_data)
            response = Response(message=request_received)
            response.set_data(payload_data)
            input_queue.put(response.encode())
            tcp_response = end_client.get_from_reception_queue(tcp_request_send)
            self.assertEqual(tcp_request_send.what, tcp_response.what)
            self.assertEqual(tcp_request_send.number, tcp_response.number)
            self.assertEqual(ErrorCodes.NO_ERROR, tcp_response.identifier)
            self.assertEqual(tcp_request_send.message_type, tcp_response.message_type)
            self.assertEqual(tcp_request_send.data_type, tcp_response.data_type)
            self.assertIs(tcp_response.get_payload_data(), payload_data)
            end_client.disconnect()
            payload_data = not payload_data
        # Wait for processes to terminate
        print('test_end_client_to_middle_server done')

    def test_middle_client_end_server(self):
        print('start of test_middle_client_end_server')
        """
        Test conditions:
            A TCPClient is running and connected to a TCPServer. Messages are put in the input queue of the client
        Expected:
            The messages passed to the queue are forwarded to the server and the responses are put in the client
            output queue
        """

        def process_request_side_effect(tcp_request, connection, address):
            tcp_response = TCPResponse(message=tcp_request)
            tcp_response.set_data(int(tcp_request.args[0]) * int(tcp_request.args[1]))
            connection.sendto(tcp_response.encode(), address)
        input_queue = Queue()
        output_queue = Queue()
        middle_client = TCPClient(ip_addr='127.0.0.1', input_queue=input_queue, output_queue=output_queue)
        end_server = TCPServer(ip_addr='127.0.0.1')
        end_server.process_request = mock.MagicMock()
        end_server.process_request.side_effect = process_request_side_effect
        request_definitions = RequestDefinitions()
        request_definitions.set(**{'Name': 'test', 'DataType': 'int', 'RequestType': 'query', 'NumberOfArguments': 2})
        request_definitions.received_definitions = True
        middle_client.queue_io.request_definitions = request_definitions
        end_server.queue_io.request_definitions = request_definitions
        end_server_process = Process(target=end_server.run)
        middle_client_process = Process(target=middle_client.run)
        end_server_process.start()
        middle_client_process.start()
        time.sleep(1)
        for i in range(0, 15):
            request = Request(what='test', message_type='query', args=[i + 1, i + 2], data_type='int', hop=3)
            input_queue.put(request.encode())
            # Make sure the hopped request is received
            hop_request_data = output_queue.get()
            hop_request = Request(encoded_data=hop_request_data)
            self.assertEqual(request.hop + 1, hop_request.hop)
            self.assertEqual(request.what, hop_request.what)
            self.assertEqual(request.number, hop_request.number)
            while True:
                response_data = output_queue.get()
                print('response_data: {}'.format(response_data))
                try:
                    response = Response(encoded_data=response_data)
                    response.data_type = 'int'
                    self.assertEqual(response.get_payload_data(), (i + 1) * (i + 2))
                    break
                except RequestException as e:
                    if e.error_code == ErrorCodes.IS_RESPONSE_ERROR:
                        pass
                    else:
                        raise e
            # time.sleep(20)
        os.kill(middle_client_process.pid, signal.SIGINT)
        os.kill(end_server_process.pid, signal.SIGINT)
        print('test_middle_client_end_server done')

    def test_home_controller_queue_io(self):
        print('start of test_home_controller_queue_io')
        num_processes = 5
        request_definitions = [RequestDefinitions() for _ in range(0, num_processes)]
        processes = {}

        def send_request_side_effect(req):
            data = req.args[0]
            response_data = 'received from ' + data
            r = Response(message=req)
            r.set_data(response_data)
            return r
        home_controller = HomeController()
        home_controller.ping = False
        member_id = 2
        for i in range(0, len(request_definitions)):
            request_definitions[i].set(**{'Name': 'req_def_{}'.format(i), 'DataType': 'str', 'NumberOfArguments': 1})
            processes['process_{}'.format(i)] = HomeController.\
                HomeControllerProcess(Name='process_{}'.format(i),
                                      request_definitions=request_definitions[i].as_dict(),
                                      input_queue=home_controller.queue_io.input_queue)
            processes['process_{}'.format(i)].ping = mock.MagicMock(return_value=0)
            processes['process_{}'.format(i)].queue_io.send_request = mock.MagicMock()
            processes['process_{}'.format(i)].queue_io.send_request.side_effect = send_request_side_effect
            processes['process_{}'.format(i)].member_id = member_id
            member_id += 1
        home_controller.processes = processes
        home_controller_process = Process(target=home_controller.run)
        home_controller_process.start()
        # swap the input and output queues
        for _, process in processes.items():
            tmp = process.queue_io.input_queue
            process.queue_io.input_queue = process.queue_io.output_queue
            process.queue_io.output_queue = tmp
        for i in range(0, num_processes):
            receiver_process = home_controller.processes['process_{}'.format(i)]
            for sender_process_name, sender_process in home_controller.processes.items():
                if sender_process is not receiver_process:
                    # Put data in output queue of sender and retreive it from the input queue of the receiver process
                    request = Request(what='req_def_{}'.format(i), message_type='query',
                                      args=[sender_process_name], data_type='str', sender_id=sender_process.member_id)
                    sender_process.queue_io.output_queue.put(request.encode())
                    time.sleep(0.5)
                    hopped_request_data = sender_process.queue_io.input_queue.get()
                    hopped_request = Request(encoded_data=hopped_request_data)
                    self.assertEqual(request.hop + 1, hopped_request.hop)
                    self.assertEqual(request.what, hopped_request.what)
                    self.assertEqual(request.number, hopped_request.number)
                    forwarded_data = receiver_process.queue_io.input_queue.get()
                    forwarded_request = Request(encoded_data=forwarded_data)
                    # Assert the HomeController incremented the request hop
                    self.assertTrue(forwarded_request.hop, request.hop + 1)
                    # Send back hopped request 5 times
                    for j in range(0, 5):
                        forwarded_request.add_hop()
                        receiver_process.queue_io.output_queue.put(forwarded_request.encode())
                        hopped_encoded_data = sender_process.queue_io.input_queue.get()
                        hopped_request = Request(encoded_data=hopped_encoded_data)
                        self.assertEqual(hopped_request.what, request.what)
                        self.assertEqual(hopped_request.number, request.number)
                    response = send_request_side_effect(forwarded_request)
                    receiver_process.queue_io.output_queue.put(response.encode())
                    sent_response_data = sender_process.queue_io.input_queue.get()
                    sent_response = Response(encoded_data=sent_response_data)
                    sent_response.data_type = 'str'
                    self.assertEqual(sent_response.get_payload_data(), 'received from ' + sender_process_name)
        os.kill(home_controller_process.pid, signal.SIGINT)
        print('test_home_controller_queue_io done')

    def test_end_client_to_end_server(self):
        print('start of test_end_client_to_end_server')
        """
        end_client -> middle_server -> home_controller -> middle_client -> end_server
        """
        max_message_number = 15
        print('Test process is {}'.format(os.getpid()))

        def process_request_side_effect(tcp_request, connection, address):
            Logger('tcp_request.data_type={} what={} number={}'.format(tcp_request.data_type,
                                                                       tcp_request.what,
                                                                       tcp_request.number), 'D')
            tcp_request.add_hop()
            res = TCPResponse(message=tcp_request)
            Logger('res.data_type={}'.format(res.data_type), 'D')
            res.set_data('Processed by end_server')
            connection.sendto(res.encode(), address)
        req_def_dict = {'test': {'Name': 'test',
                                 'DataType': 'str',
                                 'NumberOfArguments': 1},
                        'get_state': {'Name': 'get_state', 'DataType': 'str', 'NumberOfArguments': 0}}
        home_controller = HomeController()
        home_controller_processes = {
            'middle_server': HomeController.HomeControllerProcess(Name='middle_server'),
            'middle_client': HomeController.HomeControllerProcess(Name='middle_client',
                                                                  request_definitions=req_def_dict),
            'end_server': HomeController.HomeControllerProcess(Name='end_server', Address='127.0.0.1',
                                                               request_definitions=req_def_dict, Remote='true'),
        }
        home_controller_processes['middle_server'].ping = mock.MagicMock(return_value=ErrorCodes.NO_ERROR)
        home_controller_processes['middle_server'].member_id = 2
        home_controller_processes['middle_client'].ping = mock.MagicMock(return_value=ErrorCodes.NO_ERROR)
        home_controller_processes['middle_client'].member_id = 3
        home_controller_processes['end_server'].ping = mock.MagicMock(return_value=ErrorCodes.NO_ERROR)
        home_controller.processes = home_controller_processes
        middle_server_intput_queue = Queue()
        middle_server_output_queue = home_controller.queue_io.input_queue
        middle_client_intput_queue = Queue()
        middle_client_output_queue = home_controller.queue_io.input_queue
        middle_server = TCPInterfaceServer(ip_addr='127.0.0.1',
                                           input_queue=middle_server_intput_queue,
                                           output_queue=middle_server_output_queue,
                                           member_id=2)
        middle_server.socket_port = 5000
        middle_client = TCPClient(ip_addr='127.0.0.1',
                                  input_queue=middle_client_intput_queue,
                                  output_queue=middle_client_output_queue,
                                  member_id=3)
        middle_client.set_request_definitions(req_def_dict)
        end_server = TCPServer(ip_addr='127.0.0.1')
        end_server.process_request = mock.MagicMock()
        end_server.process_request.side_effect = process_request_side_effect
        # Swap the queues in home_controller
        home_controller_processes['middle_client'].queue_io.input_queue = QueueWrapper(middle_client_output_queue)
        home_controller_processes['middle_client'].queue_io.output_queue = QueueWrapper(middle_client_intput_queue)
        home_controller_processes['middle_server'].queue_io.output_queue = QueueWrapper(middle_server_intput_queue)
        home_controller_processes['middle_server'].queue_io.input_queue = QueueWrapper(middle_server_output_queue)
        home_controller_process = Process(target=home_controller.run)
        middle_server_process = Process(target=middle_server.run)
        middle_client_process = Process(target=middle_client.run)
        end_server_process = Process(target=end_server.run)
        # Start processes
        os.environ['LOG_FILE'] = '/home/maxime/logs/MiddleServerTest.log'
        middle_server_process.start()
        print('middle_server_process.pid {}'.format(middle_server_process.pid))
        os.environ['LOG_FILE'] = '/home/maxime/logs/EndServerTest.log'
        end_server_process.start()
        time.sleep(1)
        print('end_server_process.pid {}'.format(end_server_process.pid))
        home_controller.processes['end_server'].send_definitions()
        time.sleep(0.5)
        os.environ['LOG_FILE'] = '/home/maxime/logs/MiddleClientTest.log'
        middle_client_process.start()
        print('middle_client_process.pid {}'.format(middle_client_process.pid))
        time.sleep(0.5)
        os.environ['LOG_FILE'] = '/home/maxime/logs/HomeControllerTest.log'
        home_controller_process.start()
        print('home_controller_process.pid {}'.format(home_controller_process.pid))
        time.sleep(0.5)
        os.environ['LOG_FILE'] = '/home/maxime/logs/EndClientTest.log'
        end_client = TCPClient(ip_addr='127.0.0.1')
        end_client.socket_port = 5000
        end_client.set_request_definitions(req_def_dict)
        # end_client.connect = mock.MagicMock()
        for i in range(0, max_message_number):
            end_client.connect(max_attempt=1)
            print('end_client.responce_receiver_process.pid {}'.format(end_client.response_receiver_process.pid))
            response = end_client.query('test')
            print('Got response')
            end_client.disconnect()
            print('client disconnected')
            self.assertEqual(response.get_payload_data(), 'Processed by end_server')
        # Stop processes
        time.sleep(2)
        os.kill(home_controller_process.pid, signal.SIGINT)
        os.kill(middle_server_process.pid, signal.SIGINT)
        os.kill(middle_client_process.pid, signal.SIGINT)
        os.kill(end_server_process.pid, signal.SIGINT)
        # give time for processes to terminate

        print('test_end_client_to_end_server done')

    def test_end_server_hop_responses(self):
        print('start of test_end_server_hop_responses')
        req_def_dict = {'test': {'Name': 'test',
                                 'DataType': 'str',
                                 'NumberOfArguments': 1},
                        'get_state': {'Name': 'get_state', 'DataType': 'str', 'NumberOfArguments': 0}}
        home_controller = HomeController()
        home_controller.ping = False
        home_controller_processes = {
            'middle_server': HomeController.HomeControllerProcess(Name='middle_server', member_id=2),
            'middle_client': HomeController.HomeControllerProcess(Name='middle_client',
                                                                  request_definitions=req_def_dict, member_id=3),
            'end_server': HomeController.HomeControllerProcess(Name='end_server', Address='127.0.0.1',
                                                               request_definitions=req_def_dict, Remote='true'),
        }
        home_controller_processes['middle_server'].ping = mock.MagicMock(return_value=ErrorCodes.NO_ERROR)
        home_controller_processes['middle_client'].ping = mock.MagicMock(return_value=ErrorCodes.NO_ERROR)
        home_controller_processes['end_server'].ping = mock.MagicMock(return_value=ErrorCodes.NO_ERROR)
        home_controller.processes = home_controller_processes
        middle_server_intput_queue = Queue()
        middle_server_output_queue = home_controller.queue_io.input_queue
        middle_client_intput_queue = Queue()
        middle_client_output_queue = home_controller.queue_io.input_queue
        middle_server = TCPInterfaceServer(ip_addr='127.0.0.1',
                                           input_queue=middle_server_intput_queue,
                                           output_queue=middle_server_output_queue,
                                           member_id=2)
        middle_server.socket_port = 5000
        middle_client = TCPClient(ip_addr='127.0.0.1',
                                  input_queue=middle_client_intput_queue,
                                  output_queue=middle_client_output_queue,
                                  member_id=3)
        middle_client.set_request_definitions(req_def_dict)
        end_server = TCPServer(ip_addr='127.0.0.1')
        fake_results = [(None, None, False), (None, None, False),
                        (None, None, False), (None, None, False), (7, 8, True)]

        def send_command(*_args, queue=None, **_kwargs):
            nonlocal fake_results
            for fake_result in fake_results:
                time.sleep(0.5)
                queue.put(fake_result)
        end_server.command_interface.send_command = mock.MagicMock()
        end_server.command_interface.send_command .side_effect = send_command
        # Swap the queues in home_controller
        home_controller_processes['middle_client'].queue_io.input_queue = QueueWrapper(middle_client_output_queue)
        home_controller_processes['middle_client'].queue_io.output_queue = QueueWrapper(middle_client_intput_queue)
        home_controller_processes['middle_server'].queue_io.output_queue = QueueWrapper(middle_server_intput_queue)
        home_controller_processes['middle_server'].queue_io.input_queue = QueueWrapper(middle_server_output_queue)
        home_controller_process = Process(target=home_controller.run)
        middle_server_process = Process(target=middle_server.run)
        middle_client_process = Process(target=middle_client.run)
        end_server_process = Process(target=end_server.run)
        # Start processes
        os.environ['LOG_FILE'] = '/home/maxime/logs/MiddleServerTest.log'
        middle_server_process.start()
        print('middle_server_process.pid {}'.format(middle_server_process.pid))
        os.environ['LOG_FILE'] = '/home/maxime/logs/EndServerTest.log'
        end_server_process.start()
        time.sleep(1)
        print('end_server_process.pid {}'.format(end_server_process.pid))
        home_controller.processes['end_server'].send_definitions()
        time.sleep(0.5)
        os.environ['LOG_FILE'] = '/home/maxime/logs/MiddleClientTest.log'
        middle_client_process.start()
        print('middle_client_process.pid {}'.format(middle_client_process.pid))
        time.sleep(0.5)
        os.environ['LOG_FILE'] = '/home/maxime/logs/HomeControllerTest.log'
        home_controller_process.start()
        print('home_controller_process.pid {}'.format(home_controller_process.pid))
        os.environ['LOG_FILE'] = '/home/maxime/logs/EndClientTest.log'

        request = TCPRequest(what='test', message_type='command')
        request.set_definition(middle_client.get_request_definition('test'))

        # Fakse results
        expected_messages = [
            TCPRequest(what='test', message_type='command', hop=1),
            TCPRequest(what='test', message_type='command', hop=2),
            TCPRequest(what='test', message_type='command', hop=3),
            TCPRequest(what='test', message_type='command', hop=4),
        ]
        [expected_messages.append(TCPRequest(what='test', message_type='command', hop=4))
         for _ in range(0, len(fake_results) - 1)]
        expected_messages.append(TCPResponse(what='test',
                                             identifier=8,
                                             raw_data=b'7',
                                             message_type='command',
                                             hop=4))
        print(expected_messages)
        # Create socket, send request, read responses
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((middle_server.host_ipaddr, middle_server.socket_port))
        s.send(request.encode())
        messages = []
        while True:
            print('messages: {}'.format(messages))
            print('will receive')
            message_length = int.from_bytes(s.recv(TCP_MESSAGE_SIZE_LENGTH), byteorder='big')
            print('received')
            message_data = s.recv(message_length)
            print('message data {}'.format(message_data))
            if message_data[ENCODED_MESSAGE_INDENTIFIER_INDEX] == REQUEST_IDENT:
                message = Request(encoded_data=message_data)
            else:
                print(message_data)
                message = Response(encoded_data=message_data)
            messages.append(message)
            if len(messages) == len(expected_messages):
                break
        s.shutdown(socket.SHUT_RDWR)
        s.close()
        self.assertEqual(len(messages), len(expected_messages))
        for i in range(0, len(messages)):
            print(i)
            self.assertEqual(messages[i].number, request.number)
            self.assertEqual(messages[i].message_type, expected_messages[i].message_type)
            self.assertEqual(messages[i].what, expected_messages[i].what)
            self.assertEqual(messages[i].identifier, expected_messages[i].identifier)
            self.assertEqual(messages[i].raw_data, expected_messages[i].raw_data)
        # Stop processes
        os.kill(home_controller_process.pid, signal.SIGINT)
        os.kill(middle_server_process.pid, signal.SIGINT)
        os.kill(middle_client_process.pid, signal.SIGINT)
        os.kill(end_server_process.pid, signal.SIGINT)
        # give time for processes to terminate
        time.sleep(2)
        print('test_end_server_hop_responses done')

    def test_HomeController_link_queues(self):
        print('start of test_HomeController_link_queues')
        """
        Test Cases:
            1. The target response is found. The response is forwarded to the receiver output queue. All
            other messages are put back in the queue.
            2. The function times out because of inactivity. The function puts a error coded response in the
            queue. All other messages are put back in the queue.
        """
        home_controller = HomeController()
        target_reqest = Request(what='test', data_type='str', message_type='query')
        target_response = Response(message=target_reqest)
        sender = HomeController.HomeControllerProcess(**{'Name': 'sender'})
        receiver = HomeController.HomeControllerProcess(**{'Name': 'receiver'})
        sender.queue_io.piping_numbers.append(target_reqest.number)
        receiver.queue_io.piping_numbers.append(target_reqest.number)
        TcpServerClientPkg.INACTIVITY_TIMEOUT = 0
        non_matching_messages = [
            Request(what='test', data_type='str', message_type='query'),
            Request(what='test', data_type='str', message_type='query'),
            Request(what='test', data_type='str', message_type='query'),
            Request(what='test', data_type='str', message_type='query'),
            Request(what='test', data_type='str', message_type='query'),
            Request(what='test', data_type='str', message_type='query'),
            Request(what='test', data_type='str', message_type='query'),
            Request(what='test', data_type='str', message_type='query'),
            Request(what='test', data_type='str', message_type='query'),
            Request(what='test', data_type='str', message_type='query'),
        ]
        input_messages = list(non_matching_messages)
        target_request_indexes = [3, 5, 7, 9]
        for i in target_request_indexes[:-1]:
            input_messages.insert(i, target_reqest)
        input_messages.insert(target_request_indexes[-1], target_response)
        fake_sender_queue = Queue()
        fake_receiver_queue = Queue()
        sender.queue_io.input_queue = fake_sender_queue
        receiver.queue_io.output_queue = fake_receiver_queue
        [fake_sender_queue.put(r.encode()) for r in input_messages]
        home_controller.link_queues(target_reqest, receiver, sender)
        receiver_queue_content = []
        expected_sender_queue_content = [r.encode() for r in non_matching_messages]
        while not fake_receiver_queue.empty():
            receiver_queue_content.append(fake_receiver_queue.get())
            time.sleep(0.1)
        while not fake_sender_queue.empty():
            data = fake_sender_queue.get()
            if data in expected_sender_queue_content:
                del expected_sender_queue_content[expected_sender_queue_content.index(data)]
        expected_receiver_queue_content = [target_reqest.encode() for _ in target_request_indexes[:-1]] + \
                                          [target_response.encode()]
        self.assertListEqual(receiver_queue_content, expected_receiver_queue_content)
        self.assertListEqual([], expected_sender_queue_content)
        self.assertNotIn(target_reqest.number, receiver.queue_io.piping_numbers)
        self.assertNotIn(target_reqest.number, sender.queue_io.piping_numbers)

        # 2. The function times out because of inactivity. The function puts a error coded response in the
        # queue. All other messages are put back in the queue.
        sender.queue_io.piping_numbers.append(target_reqest.number)
        receiver.queue_io.piping_numbers.append(target_reqest.number)
        target_response.identifier = ErrorCodes.INACTIVITY_TIMEOUT_ERROR
        expected_receiver_queue_content = [target_response.encode()]
        [fake_sender_queue.put(r.encode()) for r in non_matching_messages]
        home_controller.link_queues(target_reqest, receiver, sender)
        time.sleep(0.1)
        expected_sender_queue_content = [r.encode() for r in non_matching_messages]
        receiver_queue_content = []
        while not fake_receiver_queue.empty():
            receiver_queue_content.append(fake_receiver_queue.get())
        while not fake_sender_queue.empty():
            data = fake_sender_queue.get()
            if data in expected_sender_queue_content:
                del expected_sender_queue_content[expected_sender_queue_content.index(data)]
        self.assertListEqual(receiver_queue_content, expected_receiver_queue_content)
        self.assertListEqual([], expected_sender_queue_content)
        self.assertNotIn(target_reqest.number, receiver.queue_io.piping_numbers)
        self.assertNotIn(target_reqest.number, sender.queue_io.piping_numbers)
        fake_sender_queue.close()
        fake_receiver_queue.close()
        print('test_HomeController_link_queues done')

    def test_connect_to_TCPInterface(self):
        print('start of test_connect_to_TCPInterface')
        server = TCPInterfaceServer()
        server.host_ipaddr = '127.0.0.1'
        server_process = Process(target=server.run)
        server_process.start()
        time.sleep(1)
        self.processes.append(server_process.pid)
        receiver_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        receiver_socket.connect(('127.0.0.1', server.socket_port))
        # send the get_state request
        get_state_request = TCPRequest(what='get_state', message_type='query', data_type='str')
        receiver_socket.send(get_state_request.encode())
        response_length = receiver_socket.recv(TCP_MESSAGE_SIZE_LENGTH)
        response_data = receiver_socket.recv(int.from_bytes(response_length, byteorder='big'))
        response = Response(encoded_data=response_data)
        self.assertEqual(response.get_payload_data(), 'READY_STATE')
        # Send connect command
        connect_request = TCPRequest(what='connect', message_type='command', data_type='int')
        receiver_socket.send(connect_request.encode())
        response_length = receiver_socket.recv(TCP_MESSAGE_SIZE_LENGTH)
        response_data = receiver_socket.recv(int.from_bytes(response_length, byteorder='big'))
        response = Response(encoded_data=response_data)
        self.assertEqual(response.get_payload_data(), ErrorCodes.COMMAND_SUCCESS)
        receiver_socket.shutdown(socket.SHUT_RDWR)
        receiver_socket.close()
        print('test_connect_to_TCPInterface done')


def send_definitions(ip_addr, definitions):
    encoded_definitions = json.dumps(definitions)
    encoded_definitions = len(encoded_definitions).to_bytes(TCP_MESSAGE_SIZE_LENGTH, byteorder='big') + \
        encoded_definitions.encode('utf-8')
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((ip_addr, SERVER_PORT))
    print(s.getsockname())
    print(s.getpeername())
    init_request = TCPRequest(what='accept_definitions', message_type='command', data_type='int')
    s.send(init_request.encode())
    s.send(encoded_definitions)
    s.send(b'')
    # Empty the socket
    s.setblocking(False)
    while True:
        try:
            s.recv(1024)
        except BlockingIOError:
            break
    s.shutdown(socket.SHUT_RDWR)
    s.close()
