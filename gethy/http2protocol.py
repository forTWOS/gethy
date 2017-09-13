import logging

import h2.config
import h2.connection
import h2.events
import h2.exceptions

from . import event_handle
from .event import RequestEvent, MoreDataToSendEvent
from .state import State, Stream, StreamSender


class HTTP2Protocol:
	"""
	A pure in-memory H2 implementation for application level development.
	
	It does not do IO.
	"""
	def __init__(self):
		self.state = State()
		self.current_events = []

		config = h2.config.H2Configuration(client_side=False, header_encoding='utf-8')
		self.http2_connection = h2.connection.H2Connection(config=config)

	def receive(self, data: bytes):
		"""
		receive bytes, return HTTP Request object if any stream is ready
		else return None
		
		:param data: bytes, received from a socket
		:return: list, of Request
		"""

		logging.debug("HTTP2Protocol receive begin")

		# First, proceed incoming data
		# handle any events emitted from h2
		events = self.http2_connection.receive_data(data)
		for event in events:
			self.handle_event(event)

		# This is a list of stream ids
		stream_to_delete_from_inbound_cache = []

		# inbound_streams is a dictionary with schema {stream_id: stream_obj}
		# therefore use .values()
		for stream in self.state.inbound_streams.values():

			logging.debug("HTTP2Protocol.receive check inbound_streams")

			if stream.stream_ended:
				logging.debug("HTTP2Protocol.receive %s %s", stream.stream_id, stream.stream_ended)

				# create a HTTP Request event, add it to current event list
				event = RequestEvent(stream)
				self.current_events.append(event)

				# Emitting an event means to clear the cached inbound data
				# The caller has to handle all returned events. Otherwise bad
				stream_to_delete_from_inbound_cache.append(stream.stream_id)

		# clear the inbound cache
		for stream_id in stream_to_delete_from_inbound_cache:
			del self.state.inbound_streams[stream_id]

		for stream_sender in self.state.outbound_streams.values():
			# todo: clear outbound data somewhere somehow
			print("HTTP2Protocol.receive check if any stream sender still cached outbound_streams")
			if not stream_sender.is_waiting_for_flow_control:
				print("HTTP2Protocol.receive", stream_sender.stream_id)
				event = MoreDataToSendEvent(stream_sender)
				self.current_events.append(event)

		events = self.current_events	# assign all current events to an events variable and return this variable
		self.current_events = []		# empty current event list by assign a newly allocated list

		logging.debug("HTTP2Protocol receive return")
		return events

	def send(self, stream: Stream):
		"""
		Prepare TCP/Socket level data to send. This function does not do IO.
		
		:param stream: a HTTP2 stream
		:return: bytes which is to send to socket 
		"""
		logging.debug("HTTP2Protocol.send stream id %d", stream.stream_id)

		stream_sender = StreamSender(stream, self.http2_connection)
		stream_sender.send(8096)

		return [MoreDataToSendEvent(data_to_send) for data_to_send in stream_sender.data_to_send]

	def handle_event(self, event: h2.events.Event):
		print("HTTP2Protocol.handle_event", type(event))
		if isinstance(event, h2.events.RequestReceived):
			event_handle.request_received(event, self.state)

		elif isinstance(event, h2.events.DataReceived):
			event_handle.data_received(event, self.state)

		elif isinstance(event, h2.events.WindowUpdated):
			event_handle.window_updated(event, self.state)

		else:
			print("Has not implement ", type(event), " handler")
