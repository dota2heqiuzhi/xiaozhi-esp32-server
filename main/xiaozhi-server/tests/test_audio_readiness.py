import asyncio
import json
from collections import deque
from queue import Queue
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from core import connection
from core.handle.textHandler.listenMessageHandler import ListenTextMessageHandler
from core.providers.asr import base as asr_base
from core.providers.asr.base import ASRProviderBase
from core.providers.asr.dto.dto import InterfaceType


class ObservedEvent(asyncio.Event):
    def __init__(self):
        super().__init__()
        self.waiting = asyncio.Event()

    async def wait(self):
        self.waiting.set()
        return await super().wait()


class RecordingASR(ASRProviderBase):
    interface_type = InterfaceType.LOCAL

    async def speech_to_text(self, *args, **kwargs):
        raise AssertionError("The test should intercept recognition before decoding")


class AudioHandshakeTests(unittest.IsolatedAsyncioTestCase):
    def make_connection(self):
        conn = connection.ConnectionHandler.__new__(connection.ConnectionHandler)
        conn.need_bind = False
        conn.bind_completed_event = ObservedEvent()
        conn.audio_ready_event = ObservedEvent()
        conn.stop_event = Event()
        conn.welcome_msg = {"type": "hello", "session_id": "test-session"}
        conn.websocket = SimpleNamespace(send=AsyncMock(), close=AsyncMock())
        conn.logger = Mock()
        conn._discard_message_with_bind_prompt = AsyncMock()
        conn.vad = Mock()
        conn.asr = SimpleNamespace(open_audio_channels=AsyncMock())
        conn.asr_audio_queue = Queue()
        conn.accepting_asr_audio = True
        conn.latest_listen_start_id = 0
        conn.active_listen_start_id = 0
        conn.conn_from_mqtt_gateway = False
        return conn

    def make_recording_connection(self):
        conn = self.make_connection()
        conn.bind_completed_event.set()
        conn.audio_ready_event.set()
        conn.loop = asyncio.get_running_loop()
        conn.asr = RecordingASR()
        conn.asr.handle_voice_stop = AsyncMock()
        conn.vad.is_vad.return_value = True
        conn.client_audio_buffer = bytearray()
        conn.client_voice_window = deque(maxlen=5)
        conn.client_have_voice = False
        conn.client_voice_stop = False
        conn.last_activity_time = 0.0
        conn.client_is_speaking = False
        conn.client_listen_mode = "auto"
        conn.asr_audio = []
        return conn

    async def test_hello_acknowledgement_waits_for_binding_and_audio_worker(self):
        conn = self.make_connection()
        finish_open = asyncio.Event()

        async def open_channels(_):
            await finish_open.wait()

        conn.asr.open_audio_channels.side_effect = open_channels
        hello = asyncio.create_task(
            conn._route_message('{"type":"hello","features":{"emoji":false}}')
        )
        await conn.bind_completed_event.waiting.wait()
        conn.websocket.send.assert_not_awaited()
        self.assertEqual(conn.features, {"emoji": False})

        conn.bind_completed_event.set()
        await conn.audio_ready_event.waiting.wait()
        audio = asyncio.create_task(conn._open_asr_audio_channels())
        await conn._route_message(b"premature packet")
        conn.websocket.send.assert_not_awaited()
        self.assertTrue(conn.asr_audio_queue.empty())

        finish_open.set()
        await audio
        await hello
        conn.websocket.send.assert_awaited_once()
        self.assertEqual(json.loads(conn.websocket.send.call_args.args[0]), conn.welcome_msg)

        await conn._route_message(b"first packet after hello")
        self.assertEqual(conn.asr_audio_queue.get_nowait(), b"first packet after hello")

    async def test_local_intent_and_prompt_are_ready_before_audio_worker(self):
        conn = self.make_connection()
        conn.loop = asyncio.get_running_loop()
        conn.config = {}
        conn.prompt_manager = SimpleNamespace(base_prompt_template="{{ base_prompt }}")
        conn.tts = SimpleNamespace(open_audio_channels=AsyncMock())
        conn._initialize_voiceprint = Mock()
        conn._initialize_memory = Mock()
        conn._init_report_threads = Mock()
        steps = []
        conn._initialize_intent = Mock(side_effect=lambda: steps.append("intent"))
        conn._init_prompt_enhancement = Mock(side_effect=lambda **_: steps.append("prompt"))
        conn.asr.open_audio_channels.side_effect = lambda _: steps.append("audio")

        await asyncio.to_thread(conn._initialize_components)
        await asyncio.wait_for(conn.audio_ready_event.wait(), timeout=1)

        self.assertEqual(steps, ["intent", "prompt", "audio"])
        conn._init_prompt_enhancement.assert_called_once_with(refresh_context=False)

    async def test_external_prompt_context_refresh_does_not_delay_audio(self):
        conn = self.make_connection()
        conn.loop = asyncio.get_running_loop()
        conn.config = {}
        conn.prompt_manager = SimpleNamespace(base_prompt_template="{{ weather_info }}")
        conn.tts = SimpleNamespace(open_audio_channels=AsyncMock())
        conn._initialize_voiceprint = Mock()
        conn._initialize_memory = Mock()
        conn._initialize_intent = Mock()
        conn._init_report_threads = Mock()
        refresh_started = asyncio.Event()
        finish_refresh = Event()

        def enhance_prompt(*, refresh_context=True):
            if refresh_context:
                conn.loop.call_soon_threadsafe(refresh_started.set)
                finish_refresh.wait(timeout=3)

        conn._init_prompt_enhancement = enhance_prompt
        initialize = asyncio.create_task(asyncio.to_thread(conn._initialize_components))
        try:
            await asyncio.wait_for(refresh_started.wait(), timeout=1)
            await asyncio.wait_for(conn.audio_ready_event.wait(), timeout=1)
            self.assertFalse(initialize.done())
        finally:
            finish_refresh.set()
            await initialize

    async def test_unbound_device_uses_binding_prompt_without_waiting_for_audio(self):
        conn = self.make_connection()
        conn.need_bind = True
        conn.bind_completed_event.set()

        await conn._route_message('{"type":"hello"}')

        conn._discard_message_with_bind_prompt.assert_awaited_once()
        conn.websocket.send.assert_not_awaited()
        conn.websocket.close.assert_not_awaited()
        self.assertFalse(conn.audio_ready_event.waiting.is_set())

    async def test_failed_audio_worker_never_acknowledges_hello(self):
        conn = self.make_connection()
        conn.bind_completed_event.set()
        conn.asr.open_audio_channels.side_effect = RuntimeError("cannot start worker")
        await conn._open_asr_audio_channels()

        with patch.object(connection, "HELLO_AUDIO_READY_TIMEOUT", 0.01):
            await conn._route_message('{"type":"hello"}')

        conn.websocket.send.assert_not_awaited()
        conn.websocket.close.assert_awaited_once_with(
            code=1013, reason="audio initialization timeout"
        )
        conn._discard_message_with_bind_prompt.assert_not_awaited()

    async def test_explicit_listen_start_clears_old_wakeup_guard(self):
        resume_task = asyncio.create_task(asyncio.Event().wait())
        conn = SimpleNamespace(
            logger=Mock(),
            just_woken_up=True,
            vad_resume_task=resume_task,
            reset_audio_states=Mock(),
        )

        await ListenTextMessageHandler().handle(conn, {"state": "start", "mode": "auto"})

        self.assertEqual(conn.client_listen_mode, "auto")
        self.assertFalse(conn.just_woken_up)
        conn.reset_audio_states.assert_called_once()
        with self.assertRaises(asyncio.CancelledError):
            await resume_task

    async def test_manual_start_and_stop_follow_audio_order_in_worker(self):
        conn = self.make_recording_connection()
        completed = asyncio.Event()
        conn.asr.handle_voice_stop.side_effect = lambda *_: completed.set()
        start = '{"type":"listen","state":"start","mode":"manual"}'
        stop = '{"type":"listen","state":"stop"}'
        packets = [b"first frame", b"last frame"]

        for message in [start, *packets, stop, b"late frame"]:
            await conn._route_message(message)
        self.assertEqual(conn.client_listen_mode, "auto")
        conn.asr.handle_voice_stop.assert_not_awaited()

        mcp_reply = '{"type":"mcp","payload":{"id":42,"result":{}}}'
        with patch.object(connection, "handleTextMessage", new_callable=AsyncMock) as handle:
            await conn._route_message(mcp_reply)
            handle.assert_awaited_once_with(conn, mcp_reply)

        await conn.asr.open_audio_channels(conn)
        try:
            await asyncio.wait_for(completed.wait(), timeout=2)
            conn.asr.handle_voice_stop.assert_awaited_once_with(conn, packets)
            self.assertEqual(conn.client_listen_mode, "manual")
            self.assertEqual(conn.asr_audio, [])
            self.assertTrue(conn.asr_audio_queue.empty())
        finally:
            conn.stop_event.set()
            await asyncio.to_thread(conn.asr_priority_thread.join, 2)

    async def test_detect_resumes_audio_admission_after_explicit_stop(self):
        conn = self.make_recording_connection()
        stop = '{"type":"listen","state":"stop"}'
        detect = '{"type":"listen","state":"detect","text":"wake"}'
        await conn._route_message(stop)
        await conn._route_message(b"frame after stop")
        with patch.object(connection, "handleTextMessage", new_callable=AsyncMock) as handle:
            await conn._route_message(detect)
            handle.assert_awaited_once_with(conn, detect)
        await conn._route_message(b"frame after detect")

        self.assertEqual(conn.asr_audio_queue.get_nowait(), stop)
        self.assertEqual(conn.asr_audio_queue.get_nowait(), b"frame after detect")
        self.assertTrue(conn.asr_audio_queue.empty())

    async def test_auto_explicit_stop_ignores_audio_without_confirmed_speech(self):
        conn = self.make_recording_connection()
        conn.asr_audio = [b"listening cue", b"silence"]

        await ListenTextMessageHandler().handle(conn, {"state": "stop"})

        conn.asr.handle_voice_stop.assert_not_awaited()
        self.assertEqual(conn.asr_audio, [])
        self.assertFalse(conn.client_voice_stop)

    async def test_new_listen_start_supersedes_an_in_flight_local_recognition(self):
        conn = self.make_recording_connection()
        conn.asr = RecordingASR()
        conn.audio_format = "pcm"
        conn.session_id = "audio-test"
        conn.voiceprint_provider = None
        old_asr_started = asyncio.Event()
        unblock_old_asr = asyncio.Event()
        chat_accepted = asyncio.Event()
        start = '{"type":"listen","state":"start","mode":"manual"}'
        stop = '{"type":"listen","state":"stop"}'

        async def transcribe(packets, *_):
            if packets == [b"older turn"]:
                old_asr_started.set()
                await unblock_old_asr.wait()
                return "旧的问题", None
            self.assertEqual(packets, [b"newer turn"])
            return "新的问题", None

        conn.asr.speech_to_text_wrapper = transcribe
        chat = AsyncMock(side_effect=lambda *args, **kwargs: chat_accepted.set())
        with patch.object(asr_base, "startToChat", chat), patch.object(
            asr_base, "enqueue_asr_report"
        ) as report:
            await conn.asr.open_audio_channels(conn)
            try:
                for message in (start, b"older turn", stop):
                    await conn._route_message(message)
                await asyncio.wait_for(old_asr_started.wait(), timeout=2)

                for message in (start, b"newer turn", stop):
                    await conn._route_message(message)
                self.assertEqual(conn.active_listen_start_id, 1)
                self.assertEqual(conn.latest_listen_start_id, 2)

                unblock_old_asr.set()
                await asyncio.wait_for(chat_accepted.wait(), timeout=2)
                chat.assert_awaited_once_with(conn, "新的问题", spoken=True)
                report.assert_called_once_with(conn, "新的问题", [b"newer turn"])
            finally:
                unblock_old_asr.set()
                conn.stop_event.set()
                await asyncio.to_thread(conn.asr_priority_thread.join, 2)

    async def test_auto_short_reply_with_fifteen_packets_reaches_asr(self):
        conn = self.make_recording_connection()
        conn.asr_audio = [b"pre-roll", b"voice 1", b"voice 2"] + [b"silence"] * 11
        expected_packets = [*conn.asr_audio, b"last silence"]
        conn.client_have_voice = True
        conn.client_voice_stop = True

        await conn.asr.receive_audio(conn, expected_packets[-1], audio_have_voice=False)

        conn.asr.handle_voice_stop.assert_awaited_once_with(conn, expected_packets)
        self.assertEqual(conn.asr_audio, [])

    async def test_streaming_controls_keep_immediate_stop_request(self):
        conn = self.make_recording_connection()
        conn.asr.interface_type = InterfaceType.STREAM
        conn.asr._send_stop_request = AsyncMock()

        await conn._route_message('{"type":"listen","state":"start","mode":"manual"}')
        self.assertEqual(conn.client_listen_mode, "manual")
        await conn._route_message('{"type":"listen","state":"stop"}')
        await asyncio.sleep(0)

        conn.asr._send_stop_request.assert_awaited_once()
        self.assertTrue(conn.client_voice_stop)
        await conn._route_message(b"streaming frame after stop")
        self.assertEqual(conn.asr_audio_queue.get_nowait(), b"streaming frame after stop")
