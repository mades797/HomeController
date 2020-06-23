import os
from TCPServerClient import TCPServer, TCPClient, TCPResponse, TCPRequest, TCPMessage, SocketWrapper
from Requests import *
from Logger import Logger
from methods import *
from threading import Thread

LOCALHOST = os.getenv('LOCALHOST', '127.0.0.1')
DEFINITIONS_FILE = os.getenv('DEFINITIONS_FILE', 'Definitions.xml')


class TCPInterfaceServer(TCPServer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.queue_io.request_definitions.received_definitions = True
        self.set_state(self.READY_STATE)
        self.routing_thread = None
        self.running = False

    def do(self):
        pass

    def run(self):
        # Start routing thread
        self.running = True
        Logger('TCPInterfaceServer.run starting routing thread', 'D')
        self.routing_thread = Thread(target=link, kwargs={'routing': self.routing,
                                                          'sender': self.queue_io.input_queue,
                                                          'forever': self.running})
        self.routing_thread.start()
        self.subprocesses.append(self.routing_thread)
        super().run()

    def stop(self):
        self.running = False
        self.queue_io.input_queue.close()
        super().stop()

    def process_request(self, tcp_request, *_):
        response = self.preprocess_request(tcp_request)
        if response:
            tcp_response = TCPResponse(message=response)
        else:
            # Forward the response to queue and send back the response
            queue_request = Request(message=tcp_request)
            Logger('TCPInterfaceServer received request {} number {}'
                   .format(queue_request.what, queue_request.number), 'D')
            queue_response = self.queue_io.send_request(queue_request)
            Logger('TCPInterfaceServer received response {} for request number {}'.format(queue_response.what,
                                                                                          queue_response.number), 'D')
            tcp_response = TCPResponse(message=queue_response)
            Logger('TCPInterfaceServer.process_request will return tcp_response {} number {} with data_type {}'
                   .format(tcp_response.what, tcp_response.number, tcp_response.data_type), 'D')
        return tcp_response

    def handle_connection(self, connection, address, pipe=None):
        Logger('TCPInterfaceServer.handle_connection starting', 'D')
        connection = SocketWrapper(connection, address)
        while connection:
            message_data = self.get_socket_data(connection)
            if message_data:
                Logger('TCPInterfaceServer.handle_connection got data from socket: {}'.format(message_data), 'D')
                request = Request(encoded_data=message_data)
                request.sender_id = self.member_id
                response = self.preprocess_request(request)
                if response:
                    connection.sendto(TCPResponse(message=response).encode(), address)
                else:
                    request.add_hop()
                    # Respond to the socket with the request with added hop number
                    Logger('TCPInterfaceServer.handle_connection adding message number to routing', 'D')
                    connection.sendto(TCPRequest(message=request).encode(), address)
                    self.routing[request.number] = connection
                    Logger('TCPInterfaceServer.handle_connection will write request number {} to pipe'
                           ''.format(request.number), 'D')
                    # os.write(pipe, int.to_bytes(request.number, ENCODED_MESSAGE_NUMBER_LENGTH, byteorder='big')
                    #          + b'\x01')
                    # Forward the message to the queue
                    Logger('TCPInterfaceServer.handle_connection sent back the request {} with added hop '
                           'number. Will forward the request to output queue'.format(request), 'D')
                    self.queue_io.output_queue.put(request.encode())
                    # Plug the input queue data to the socket
                    # self.queue_io.piping_numbers.append(request.number)
                    # link(sender=self.queue_io.input_queue, receiver=connection,
                    #      receiver_address=address, target_request=request,
                    #      receiver_piping_numbers=self.queue_io.piping_numbers)
                    # self.queue_to_socket(connection, address, request, pipe)
            else:
                Logger('TCPInterfaceServer.handle_connection received empty message data. Will break from loop', 'D')
                connection.finish()
                break
        # self.set_state(self.CONNECTED_STATE)
        # try:
        #     message_size = connection.recv(TCP_MESSAGE_SIZE_LENGTH)
        #     if message_size:
        #         message_data = connection.recv(int.from_bytes(message_size, byteorder='big'))
        #         Logger('Received data: {}'.format(message_data), 'D')
        #         tcp_request = self.reconstruct_request(message_data)
        #         Logger(
        #             'TCPServer.handle_connection reconstructed tcp_request {} number {} with data type {}'.format(
        #                 tcp_request.what, tcp_request.number, tcp_request.data_type), 'D')
        #         if tcp_request.is_ping():
        #             connection.sendto(TCPResponse(message=PingResponse(tcp_request)).encode(), address)
        #         elif tcp_request.is_get_state():
        #             tcp_response = TCPResponse(message=tcp_request)
        #             tcp_response.data_type = 'str'
        #             tcp_response.set_data(self.state)
        #             connection.sendto(tcp_response.encode(), address)
        #         else:
        #             Logger('Calling process_request', 'D')
        #             response = self.process_request(tcp_request)
        #             Logger(
        #                 'TCPServer.handle_connection got response {} number {} with data_type {} from
        #                 TCPServer.process_request'.format(
        #                     response.what, response.number, response.data_type), 'D')
        #             tcp_response = TCPResponse(message=response)
        #             # tcp_response = TCPResponse(message=tcp_request)
        #             # tcp_response.set_data('ALL_OK')
        #             Logger(
        #                 'Processed request number {} with data type {}. Encoding and sending response
        #                 with data type {}'.format(
        #                     tcp_request.number, tcp_request.data_type, tcp_response.data_type),
        #                 'D')
        #             connection.sendto(tcp_response.encode(), address)
        #             Logger('Response for request {} number {} sent with error code {}'
        #                    .format(tcp_request.what, tcp_request.number, tcp_response.error_code), 'D')
        #     else:
        #         # connection.close()
        #         break
        # except KeyboardInterrupt:
        #     break

    def process_input_queue(self):
        self.read_request_number_pipe()
        request = self.queue_io.get_input_message()
        if request and request.is_ping():
            self.queue_io.send_response(PingResponse(ping_request=request))
        # elif request:
        #     # Put back request in input queue
        #     Logger('TCPInterfaceServer got request {} number {} hop {} from input queue. Puting back in input '
        #            'queue'.format(request.what, request.number, request.hop), 'D')
        #     self.queue_io.input_queue.put(request.encode())
        #     time.sleep(2)

    def reconstruct_request(self, encoded_data):
        return TCPRequest(encoded_data=encoded_data)


class TCPInterfaceClient(TCPClient):
    def __init__(self, app_name='TCPInterface'):
        super().__init__(ip_addr=LOCALHOST, def_file=DEFINITIONS_FILE, app_name=app_name)
        self.queue_io.request_definitions.read_request_definitions(DEFINITIONS_FILE, 'TCPInterface')


if __name__ == '__main__':
    APP_NAME = os.getenv('APP_NAME')
    tcp_interface_server = TCPInterfaceServer(ip_addr=LOCALHOST, def_file=DEFINITIONS_FILE, app_name=APP_NAME)
    tcp_interface_server.run()
