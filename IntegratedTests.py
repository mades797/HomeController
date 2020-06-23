from unittest import mock, TestCase
from HomeController import HomeController
from TCPServerClient import *
from TCPInterface import TCPInterfaceServer

DEFAULT_HOME_CONTROLLER_DIR = '/home/maxime/PycharmProjects'


class HomeControllerIntegratedTests(TestCase):

    def setUp(self) -> None:
        self.client = TCPClient(def_file=os.path.join(os.getenv('HOME_CONTROLLER_DIR') or DEFAULT_HOME_CONTROLLER_DIR,
                                                      'HomeController',
                                                      'Definitions.xml'),
                                ip_addr='127.0.0.1', app_name='MediaController')

    def tearDown(self) -> None:
        self.client.disconnect()

    # def test_media_controller_server(self):
    #     client = TCPClient(ip_addr='RPIMediaController1.avadakedavra.net', def_file='/home/maxime/PycharmProjects/HomeController/Definitions.xml', app_name='MediaController')
    #     # client.connect()
    #     ping_response = client.ping_server()
    #     self.assertEqual(ping_response.identifier, ErrorCodes.DEFINITIONS_NOT_RECEIVED_ERROR)
    #     client.send_definitions()
    #     ping_response = client.ping_server()
    #     self.assertEqual(ping_response.identifier, ErrorCodes.COMMAND_SUCCESS)

    def test_media_controller(self):
        """
        Test conditions:
            1. Test video is played
            2. Test video is paused
            3. Test video is unpaused
            4. Test video duration is queried
            5. Test video position is set to 50% of duration
            6. Volume is set to 50%
            7. Subtitles are toggled
            8. Volume is turned up
            9. Volume is turned down
            10. Test video is played again
            11. Video is stopped
        Expected:
            1. Assert the video is being played
            2. Assert the video is paused
            3. Assert the video is not paused
            5. Assert the video position is more then 50%
            6. Assert volume is 50%
            7. Assert the response error code is NO_ERROR
            8. Assert volume is turned up
            9. Assume volume is turned down
            10. Assert video position is less then 50%
            11. Assert video is stopped
        """
        # Play test video
        test_video = '/hdd/media/test.mp4'
        client = TCPClient(def_file=os.path.join(os.getenv('HOME_CONTROLLER_DIR'),
                                                 'HomeController',
                                                 'Definitions.xml'),
                           ip_addr='127.0.0.1', app_name='MediaController')
        client.connect()
        # 1. Test video is played
        print('1. Test video is played')
        play_response = client.command('play', test_video)
        self.assertEqual(play_response.identifier, ErrorCodes.NO_ERROR)
        client.message_number = 999
        time.sleep(3)
        self.assertEqual(client.query('current_media_path').get_payload_data(), test_video)
        client.disconnect()

        # 2. Test video is paused
        print('2. Test video is paused')
        client.connect()
        client.message_number = 545
        response = client.command('play_pause')
        self.assertEqual(response.identifier, ErrorCodes.NO_ERROR)
        self.assertEqual(response.get_payload_data(), ErrorCodes.COMMAND_SUCCESS)
        # Assert the video is paused
        self.assertTrue(client.query('current_media_paused').get_payload_data())
        # 3. Test video is unpaused
        print('3. Test video is unpaused')
        client.message_number = 696
        unpause_response = client.command('play_pause')
        self.assertEqual(unpause_response.identifier, ErrorCodes.NO_ERROR)
        # Assert the video is not paused
        self.assertFalse(client.query('current_media_paused').get_payload_data())
        client.disconnect()
        # 4. Test video duration is queried
        print('4. Test video duration is queried')
        client.connect()
        client.message_number = 1234
        media_duration_response = client.query('current_media_duration')
        self.assertEqual(media_duration_response.identifier, ErrorCodes.NO_ERROR)
        media_duration = media_duration_response.get_payload_data()
        half_duration = int(round(media_duration / 2))
        # Put media back to beggining
        response = client.command('set_position', 0)
        self.assertEqual(response.identifier, ErrorCodes.NO_ERROR)
        self.assertEqual(response.get_payload_data(), ErrorCodes.COMMAND_SUCCESS)
        media_position_response = client.query('current_media_position')
        self.assertEqual(media_duration_response.identifier, ErrorCodes.NO_ERROR)
        media_position = media_position_response.get_payload_data()
        self.assertTrue(media_position < half_duration)
        # 5. Test video position is set to 50% of duration
        print('5. Test video position is set to 50% of duration')
        set_position_response = client.command('set_position', str(half_duration))
        self.assertEqual(set_position_response.get_payload_data(), ErrorCodes.COMMAND_SUCCESS)
        self.assertEqual(set_position_response.identifier, ErrorCodes.NO_ERROR)
        media_position = client.query('current_media_position').get_payload_data()
        self.assertTrue(media_position > half_duration)
        client.disconnect()
        # 6. Volume is set to 50%
        print('6. Volume is set to 50%')
        client.connect()
        set_volume_response = client.command('set_volume', '0.5')
        self.assertEqual(set_volume_response.get_payload_data(), ErrorCodes.COMMAND_SUCCESS)
        self.assertEqual(set_volume_response.identifier, ErrorCodes.NO_ERROR)
        get_volume_response = client.query('current_media_volume')
        self.assertEqual(get_volume_response.identifier, ErrorCodes.NO_ERROR)
        self.assertEqual(get_volume_response.get_payload_data(), 0.5)
        client.disconnect()
        # 7. Subtitles are toggled
        print('7. Subtitles are toggled')
        client.connect()
        subtitles_response = client.command('toggle_subtitles')
        self.assertEqual(subtitles_response.identifier, ErrorCodes.NO_ERROR)
        self.assertEqual(subtitles_response.get_payload_data(), ErrorCodes.COMMAND_SUCCESS)
        # 8. Volume is turned up
        print('8. Volume is turned up')
        volume = client.query('current_media_volume').get_payload_data()
        volume_up_command = client.command('volume_up')
        self.assertEqual(volume_up_command.identifier, ErrorCodes.NO_ERROR)
        self.assertEqual(volume_up_command.get_payload_data(), ErrorCodes.COMMAND_SUCCESS)
        volume_2 = client.query('current_media_volume').get_payload_data()
        self.assertGreater(volume_2, volume)
        # 9. Volume is turned down
        print('9. Volume is turned down')
        volume_down_command = client.command('volume_down')
        self.assertEqual(volume_down_command.identifier, ErrorCodes.NO_ERROR)
        self.assertEqual(volume_down_command.get_payload_data(), ErrorCodes.COMMAND_SUCCESS)
        volume_3 = client.query('current_media_volume').get_payload_data()
        self.assertGreater(volume_2, volume_3)
        client.disconnect()
        # 10. Test video is played again
        print('10. Test video is played again')
        client.connect()
        play_response = client.command('play', test_video)
        self.assertEqual(play_response.identifier, ErrorCodes.NO_ERROR)
        self.assertEqual(play_response.get_payload_data(), ErrorCodes.COMMAND_SUCCESS)
        # 11. Video is stopped
        print('11. Video is stopped')
        client.message_number = 90909
        stop_response = client.command('stop')
        self.assertEqual(stop_response.get_payload_data(), ErrorCodes.COMMAND_SUCCESS)
        self.assertEqual(stop_response.identifier, ErrorCodes.NO_ERROR)
        time.sleep(3)
        current_path_response = client.query('current_media_path')
        self.assertEqual(current_path_response.get_payload_data(), '')
        self.assertEqual(current_path_response.identifier, ErrorCodes.NO_ERROR)
        client.disconnect()
        print('test_media_controller done')

    def test_media_controller_play(self):
        test_video = '/hdd/media/test.mp4'
        client = self.client
        client.connect()
        # 1. Test video is played
        print('# 1. Test video is played')
        play_response = client.command('play', test_video)
        self.assertEqual(play_response.identifier, ErrorCodes.NO_ERROR)
        client.message_number = 999
        self.assertEqual(client.query('current_media_path').get_payload_data(), test_video)

        # stop the media
        stop_response = client.command('stop')
        self.assertEqual(stop_response.identifier, ErrorCodes.NO_ERROR)
        self.assertEqual(stop_response.get_payload_data(), ErrorCodes.COMMAND_SUCCESS)
        time.sleep(3)

        # Assert there is no media playing
        self.assertEqual(client.query('current_media_path').get_payload_data(), '')

        # Play media at 2 minutes
        print('# Play media at 2 minutes')
        offset = 2 * 60
        client.message_number = 4321
        play_response = client.command('play', test_video, offset)
        self.assertEqual(play_response.identifier, ErrorCodes.NO_ERROR)
        self.assertEqual(play_response.get_payload_data(), ErrorCodes.COMMAND_SUCCESS)
        # Assert the media position is more then offset
        position_response = client.query('current_media_position')
        self.assertEqual(position_response.identifier, ErrorCodes.NO_ERROR)
        self.assertGreater(position_response.get_payload_data(), offset)

        # Stop the media
        stop_response = client.command('stop')
        self.assertEqual(stop_response.identifier, ErrorCodes.NO_ERROR)
        self.assertEqual(stop_response.get_payload_data(), ErrorCodes.COMMAND_SUCCESS)
        time.sleep(3)

        # Assert not media is playing
        print('# Assert not media is playing')
        path_response = client.query('current_media_path')
        self.assertEqual(path_response.identifier, ErrorCodes.NO_ERROR)
        self.assertEqual(path_response.get_payload_data(), '')
        client.disconnect()
        print('test_media_controller_play done')

    def test_stability(self):
        client = self.client
        number_connections = 50
        for i in range(0, number_connections):
            client.connect()
            path_response = client.query('current_media_path')
            self.assertEqual(path_response.identifier, ErrorCodes.NO_ERROR)
            print('Connection number: {}. Path: {}'.format(i, path_response.get_payload_data()))
            client.disconnect()
