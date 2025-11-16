import utils.stm32_crc as stm32_crc
import struct
import time


class ResourcePack(object):
    """ Pebble resource pack file format (de)serialization tools.

        An instance of this class is an in-memory representation of a resource
        pack. The class has a number of methods to facilitate (de)serialization
        of .pbpack files.

    """

    MAX_NUM_FILES = 256
    TABLE_ENTRY_FMT = '<IIII'
    TABLE_ENTRY_SIZE_BYTES = 16
    MANIFEST_FMT = '<III'
    MANIFEST_SIZE_BYTES = 12
    CONTENT_START_OFFSET = MANIFEST_SIZE_BYTES +  MAX_NUM_FILES * TABLE_ENTRY_SIZE_BYTES

    def serialize_manifest(self, crc=None, timestamp=None):
        if crc is None:
            all_contents = b"".join(self.contents)
            crc = stm32_crc.crc32(all_contents)
        if timestamp is None:
            timestamp = self.timestamp
        fmt = self.MANIFEST_FMT
        return struct.pack(fmt, len(self.table), crc, timestamp)

    def serialize_table(self):
        def make_entry(file_id, offset, length, content):
            crc = 0 if content is None else stm32_crc.crc32(content)
            fmt = self.TABLE_ENTRY_FMT
            return struct.pack(fmt, file_id, offset, length, crc)

        if (len(self.table) > self.MAX_NUM_FILES):
            raise Exception("Exceeded max number of resources. Must have %d or "
                            "fewer" % self.MAX_NUM_FILES)

        offset = 0
        max_offset = 0
        cur_file_id = 1
        table = b''
        entry_offsets = [-1] * len(self.table)
        last_resource_match_prev = False
        for cur_file_id, table_id in enumerate(self.table, start=1):
            # if we've already got an offset for this table entry, use it
            cur_offset = entry_offsets[table_id] if entry_offsets[table_id] != -1 else offset
            # lookup content in contents table
            content = self.contents[table_id]
            length = len(content)
            # serialize entry
            table += make_entry(cur_file_id, cur_offset, length, content)
            # update offset value & entry_offsets accordingly
            offset += 0 if entry_offsets[table_id] != -1 else length
            last_resource_match_prev = True if entry_offsets[table_id] != -1 else False
            entry_offsets[table_id] = cur_offset

        if last_resource_match_prev:
            raise Exception("The last resource cannot be identical to a previous one")

        # pad the rest of the file
        for i in range(cur_file_id, self.MAX_NUM_FILES):
            table += make_entry(0, 0, 0, None)

        return table

    def serialize_content(self):
        return b"".join(self.contents)

    @classmethod
    def deserialize(cls, f_in):
        # Parse manifest:
        manifest = f_in.read(cls.MANIFEST_SIZE_BYTES)
        fmt = cls.MANIFEST_FMT
        (num_files, crc, timestamp) = struct.unpack(fmt, manifest)

        resource_pack = cls()

        # Parse table entries:
        resource_pack.table_entries = []
        for n in range(num_files):
            table_entry = f_in.read(cls.TABLE_ENTRY_SIZE_BYTES)
            fmt = cls.TABLE_ENTRY_FMT
            file_id, offset, length, crc = struct.unpack(fmt, table_entry)
            if file_id == 0:
                break
            if file_id != n + 1:
                raise Exception("File ID is expected to be %u, but was %u" %
                                (n + 1, file_id))
            resource_pack.table_entries.append((offset, length, crc))
        if len(resource_pack.table_entries) != num_files:
            raise Exception("Number of files in manifest is %u, but actual"
                            "number is %u" % (num_files, n))

        # Fetch the contents:
        for entry in resource_pack.table_entries:
            offset, length, crc = entry
            f_in.seek(offset + cls.CONTENT_START_OFFSET)
            content = f_in.read(length)
            calculated_crc = stm32_crc.crc32(content)
            if calculated_crc != crc:
                raise Exception("Entry %s does not match CRC of content (0x%x)"
                                % (entry, calculated_crc))
            resource_pack.contents.append(content)

        resource_pack.num_files = num_files
        resource_pack.timestamp = timestamp
        return resource_pack

    def serialize(self, f_out):
        all_contents = b"".join(self.contents)
        crc = stm32_crc.crc32(all_contents)
        table = self.serialize_table()
        manifest = self.serialize_manifest(crc)
        f_out.write(manifest)
        f_out.write(table)
        f_out.write(all_contents)
        return crc

    def add_resource(self, content):
        index = -1
        # if resource already is present, add to table only
        try:
            if (len(content) != 0):
                index = self.contents.index(content)
            else:
                raise ValueError
        except ValueError:
            self.contents.append(content)
            index = len(self.contents) - 1
        self.table.append(index)

    def __init__(self):
        self.num_files = 0
        self.timestamp = int(time.time())
        self.contents = []
        self.table_entries = []
        self.table = []
        self.is_v2 = True
