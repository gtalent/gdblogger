
import json

class Field(dict):
    name = ''
    value = None
    type = ''
    def __init__(self, name, value, field_type):
        self.name = name
        self.value = value
        if field_type == gdb.TYPE_CODE_STRUCT:
            self.type = 'struct'
        elif field_type == gdb.TYPE_CODE_UNION:
            self.type = 'union'
        elif field_type == gdb.TYPE_CODE_ENUM:
            self.type = 'enum'
        elif field_type == gdb.TYPE_CODE_ARRAY:
            self.type = 'enum'
        else:
            self.type = 'scalar'
        dict.__init__(self, name=name, value=value, type=self.type)

class Frame(dict):
    trace_msg = ''
    function = ''
    file_name = ''
    line_number = 0
    fields = []
    def __init__(self, trace_msg, function, file_name, line_number, fields):
        dict.__init__(self, trace_msg=trace_msg, function=function, \
                      file_name=file_name, line_number=line_number, fields=fields)

class Executor:
    def __init__(self, cmd):
        self.__cmd = cmd

    def __call__(self):
        gdb.execute(self.__cmd)

def has_fields(t):
    return t.code == gdb.TYPE_CODE_STRUCT or t.code == gdb.TYPE_CODE_UNION \
           or t.code == gdb.TYPE_CODE_ENUM

def build_value(value):
    t = value.type
    if t is not None:
        if has_fields(t):
            fields = []
            if t.keys() is not None:
                for key in t.keys():
                    val = value[key]
                    fields.append(Field(key, build_value(val), val.type.code))
            return fields
        elif t.code == gdb.TYPE_CODE_ARRAY:
            fields = []
            if t.fields() is not None:
                r = t.range()
                for i in range(r[0], r[1] + 1):
                    fields.append(Field(i, build_value(value[i]), value[i].type.code))
            return fields
        else:
            # parse as string
            return str(value)

def frame_source_line(bt, level):
    f = bt[level].split(' ')
    source_line = f[len(f)-1].split(':')
    file = source_line[0]
    line = int(source_line[1])
    return (file, line)

def handle_tracepoint(event):
    gdb.execute("set scheduler-locking on")
    # iterate over frames
    gdb.newest_frame()
    cur_frame = gdb.selected_frame()
    print('Frames')
    frame_no = 0
    frames = []
    bt = gdb.execute('bt', to_string=True).split('\n')
    bt.pop()
    while cur_frame is not None:
        cur_frame.select()
        function = cur_frame.name()
        source_line = frame_source_line(bt, frame_no)
        file_name = source_line[0]
        line_number = source_line[1]
        fields = []
        frame_symbols = set()
        print('{}: {}'.format(frame_no, cur_frame.name()))
        print('\tArchitecture: ' + cur_frame.architecture().name())
        # iterate over blocks
        print('\tVariables:')
        block = cur_frame.block()
        log_msg = ''
        while block is not None:
            # iterate over symbols
            for symbol in block:
                field_name = symbol.name
                if (symbol.is_argument or symbol.is_variable or symbol.is_constant) \
                   and not field_name in frame_symbols and symbol.line < line_number:
                    #print(help(symbol.symtab))
                    sym_val = symbol.value(cur_frame)
                    field_value = build_value(sym_val)
                    if field_name == 'ox::trace::debugger::logMsg':
                        log_msg = field_value
                    else:
                        fields.append(Field(field_name, field_value, sym_val.type.code))
                        #print('\t\t{}: {}'.format(field_name, json.dumps(field_value)))
                        frame_symbols.add(field_name)
            # end: iterate over symbols
            block = block.superblock
        # end: iterate over blocks
        cur_frame = cur_frame.older()
        frames.append(Frame(log_msg, function, file_name, line_number, fields))
        frame_no += 1
    # end: iterate over frames
    gdb.execute("set scheduler-locking off")
    gdb.post_event(Executor("continue"))
    print(json.dumps(frames, indent=4, separators=(',', ': ')))
    print("Finished safely")

def handle_exit(event):
    gdb.post_event(Executor("quit"))

gdb.events.stop.connect(handle_tracepoint)
gdb.events.exited.connect(handle_exit)
