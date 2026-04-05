"""飞书 WebSocket protobuf 协议"""
from google.protobuf.internal import decoder


class PbFrame:
    def __init__(self):
        self.seq_id = 0
        self.log_id = 0
        self.service = 0
        self.method = 0
        self.headers = {}
        self.payload = None

    @staticmethod
    def parse(data: bytes):
        frame = PbFrame()
        pos = 0
        while pos < len(data):
            tag, pos = decoder._DecodeVarint(data, pos)
            field_num = tag >> 3

            if field_num == 1:  # seq_id
                frame.seq_id, pos = decoder._DecodeVarint(data, pos)
            elif field_num == 2:  # log_id
                frame.log_id, pos = decoder._DecodeVarint(data, pos)
            elif field_num == 3:  # service
                frame.service, pos = decoder._DecodeSignedVarint32(data, pos)
            elif field_num == 4:  # method
                frame.method, pos = decoder._DecodeSignedVarint32(data, pos)
            elif field_num == 5:  # headers (repeated)
                length, pos = decoder._DecodeVarint(data, pos)
                header_data = data[pos:pos + length]
                key, value = PbFrame._parse_header(header_data)
                frame.headers[key] = value
                pos += length
            elif field_num == 8:  # payload
                length, pos = decoder._DecodeVarint(data, pos)
                frame.payload = data[pos:pos + length]
                pos += length
            else:
                # 跳过未知字段
                wire_type = tag & 7
                if wire_type == 0:
                    _, pos = decoder._DecodeVarint(data, pos)
                elif wire_type == 2:
                    length, pos = decoder._DecodeVarint(data, pos)
                    pos += length
        return frame

    @staticmethod
    def _parse_header(data: bytes):
        key = value = ""
        pos = 0
        while pos < len(data):
            tag, pos = decoder._DecodeVarint(data, pos)
            field_num = tag >> 3
            if field_num == 1:  # key
                length, pos = decoder._DecodeVarint(data, pos)
                key = data[pos:pos + length].decode('utf-8')
                pos += length
            elif field_num == 2:  # value
                length, pos = decoder._DecodeVarint(data, pos)
                value = data[pos:pos + length].decode('utf-8')
                pos += length
        return key, value

    def encode_ack(self) -> bytes:
        """生成 ACK 响应"""
        result = b""
        # seq_id (field 1)
        result += bytes([0x08]) + self._encode_varint(self.seq_id)
        # log_id (field 2)
        result += bytes([0x10]) + self._encode_varint(self.log_id)
        return result

    @staticmethod
    def _encode_varint(value: int) -> bytes:
        result = []
        while value > 0x7f:
            result.append((value & 0x7f) | 0x80)
            value >>= 7
        result.append(value & 0x7f)
        return bytes(result)

