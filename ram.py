from nmigen import *
from nmigen.back.pysim import *

###############
# RAM module: #
###############

# Data input width definitions.
RAM_DW_8  = 3
RAM_DW_16 = 2
RAM_DW_32 = 0

class RAM( Elaboratable ):
  def __init__( self, size_words ):
    # Record size.
    self.size = ( size_words * 4 )
    # Address bits to select up to `size_words * 4` bytes.
    # (+1 to detect edge-case out-of-range writes)
    self.addr = Signal( range( self.size + 1 ), reset = 0 )
    # Data word output.
    self.dout = Signal( 32, reset = 0x00000000 )
    # Data word input.
    self.din  = Signal( 32, reset = 0x00000000 )
    # Width of data input.
    self.dw   = Signal( 2, reset = 0b00 )
    # 'Write Enable' input bit.
    self.wen  = Signal( 1, reset = 0b0 )
    # 'Write wait-state' bit.
    # Mis-aligned data must be read before re-writing.
    self.wws  = Signal( 1, reset = 0b0 )
    # Data storage.
    self.data = Memory( width = 32, depth = ( self.size // 4 ),
      init = ( 0x000000 for i in range( self.size // 4 ) ) )
    # Use two r/w ports to allow mis-aligned access
    self.rd1 = self.data.read_port()
    self.rd2 = self.data.read_port()
    self.wd1 = self.data.write_port()
    self.wd2 = self.data.write_port()

  def elaborate( self, platform ):
    # Core RAM module.
    m = Module()
    m.submodules.rd1 = self.rd1
    m.submodules.rd2 = self.rd2
    m.submodules.wd1 = self.wd1
    m.submodules.wd2 = self.wd2

    # Reset write data and wait-states when not in use, and
    # disable writes by default.
    m.d.comb += [
      self.wd1.en.eq( 0 ),
      self.wd2.en.eq( 0 ),
      self.wd1.data.eq( 0 ),
      self.wd2.data.eq( 0 ),
      self.dout.eq( 0 )
    ]
    m.d.sync += [
      self.wws.eq( 0 ),
    ]

    # Set the 'dout' value based on address and RAM data.
    # (Return 0 if the address is out of range.)
    with m.If( self.addr >= self.size ):
      m.d.comb += self.dout.eq( 0x00000000 )
    # Word-aligned reads.
    with m.Elif( ( self.addr & 0b11 ) == 0b00 ):
      m.d.comb += [
        self.rd1.addr.eq( self.addr >> 2 ),
        self.dout.eq( self.rd1.data )
      ]
    # Partially out-of-bounds reads.
    with m.Elif( ( self.addr + 4 ) >= self.size ):
      m.d.comb += [
        self.rd1.addr.eq( self.addr >> 2 ),
        self.dout.eq( self.rd1.data >> ( ( self.addr & 0b11 ) << 3 ) )
      ]
    # Mis-aligned reads.
    with m.Else():
      m.d.comb += [
        self.rd1.addr.eq( self.addr >> 2 ),
        self.rd2.addr.eq( ( self.addr >> 2 ) + 1 ),
        self.dout.eq(
          ( self.rd1.data >> ( ( self.addr & 0b11 ) << 3 ) ) |
          ( self.rd2.data << ( ( 32 - ( ( self.addr & 0b11 ) << 3 ) ) ) ) )
      ]

    # Write the 'din' value if 'wen' is set.
    with m.If( self.wen ):
      # (nop if the write address is out of range.)
      with m.If( self.addr >= self.size ):
        pass
      # Word-aligned 32-bit writes.
      with m.Elif( ( ( self.addr & 0b11 ) == 0b00 ) & ( self.dw == RAM_DW_32 ) ):
        m.d.comb += [
          self.wd1.addr.eq( self.addr >> 2 ),
          self.wd1.en.eq( 1 ),
          self.wd1.data.eq( self.din )
        ]
      # Writes requiring wait-states:
      with m.Elif( self.wws == 0 ):
        m.d.sync += self.wws.eq( self.wws + 1 )
      with m.Else():
        m.d.sync += self.wws.eq( 0 )
        # Word-aligned partial writes.
        with m.If( ( self.addr & 0b11 ) == 0b00 ):
          m.d.comb += [
            self.wd1.addr.eq( self.addr >> 2 ),
            self.wd1.en.eq( 1 ),
            self.wd1.data.eq( self.rd1.data | ( self.din & ( 0xFFFFFFFF >> ( self.dw << 3 ) ) ) )
          ]
        # Partially out-of-bounds writes.
        with m.Elif( ( self.addr + 4 ) >= self.size ):
          # Assume that 'rd1' holds current data from the same address.
          m.d.comb += [
            self.wd1.addr.eq( self.addr >> 2 ),
            self.wd1.en.eq( 1 ),
            self.wd1.data.eq( ( self.rd1.data &
              ~( ( 0xFFFFFFFF >> ( self.dw << 3 ) ) << ( ( self.addr & 0b11 ) << 3 ) ) ) |
              ( self.din << ( ( ( self.addr & 0b11 ) << 3 ) ) ) )
          ]
        # Mis-aligned writes.
        with m.Else():
          # Assume that read ports hold data from the same addresses.
          m.d.comb += [
            self.wd1.addr.eq( self.addr >> 2 ),
            self.wd2.addr.eq( ( self.addr >> 2 ) + 1 ),
            self.wd1.en.eq( 1 ),
            self.wd2.en.eq( 1 ),
            self.wd1.data.eq( ( self.rd1.data &
              ~( ( 0xFFFFFFFF >> ( self.dw << 3 ) ) << ( ( self.addr & 0b11 ) << 3 ) ) ) |
              ( self.din << ( ( ( self.addr & 0b11 ) << 3 ) ) ) ),
            self.wd2.data.eq( ( self.rd2.data &
              ~( ( 0xFFFFFFFF << ( self.dw << 3 ) ) >> ( 32 - ( ( self.addr & 0b11 ) << 3 ) ) ) ) |
              ( self.din >> ( ( 32 - ( ( self.addr & 0b11 ) << 3 ) ) ) ) ),
            #self.wd2.data.eq( ( self.rd2.data &
            #  ( 0xFFFFFFFF << ( 32 - ( ( self.addr & 0b11 ) << 3 ) ) ) ) |
            #  ( self.din >> ( 32 - ( ( self.addr & 0b11 ) << 3 ) ) ) )
            #self.wd2.data.eq( self.rd2.data ),
            #self.wd1.data.eq( self.rd1.data | ( self.din >> ( ( self.addr & 0b11 ) << 3 ) ) ),
            #self.wd2.data.eq( self.rd2.data | ( self.din << ( 32 - ( ( self.addr & 0b11 ) << 3 ) ) ) )
          ]
      '''
      # Write the requested word of data.
      m.d.comb += [
        self.wd1.addr.eq( self.addr ),
        self.wd1.en.eq( 1 )
      ]
      m.d.sync += self.wd1.data.eq( self.din & 0x000000FF )
      with m.If( self.dw > 0 ):
        m.d.comb += [
          self.wd2.addr.eq( self.addr + 1 ),
          self.wd2.en.eq( 1 )
        ]
        m.d.sync += self.wd2.data.eq( ( self.din & 0x0000FF00 ) >> 8 )
      with m.If( self.dw > 1 ):
        m.d.comb += [
          self.wd3.addr.eq( self.addr + 2 ),
          self.wd4.addr.eq( self.addr + 3 ),
          self.wd3.en.eq( 1 ),
          self.wd4.en.eq( 1 )
        ]
        m.d.sync += [
          self.wd3.data.eq( ( self.din & 0x00FF0000 ) >> 16 ),
          self.wd4.data.eq( ( self.din & 0xFF000000 ) >> 24 )
        ]
      '''

    # End of RAM module definition.
    return m

##################
# RAM testbench: #
##################
# Keep track of test pass / fail rates.
p = 0
f = 0

# Perform an individual RAM write unit test.
def ram_write_ut( ram, address, data, dw, success ):
  global p, f
  # Set addres, 'din', and 'wen' signals.
  yield ram.addr.eq( address )
  yield ram.din.eq( data )
  yield ram.wen.eq( 1 )
  yield ram.dw.eq( dw )
  # Wait two ticks, and un-set the 'wen' bit.
  yield Tick()
  yield Tick()
  yield Tick()
  yield ram.wen.eq( 0 )
  # Done. Check that the 'din' word was successfully set in RAM.
  yield Settle()
  actual = yield ram.dout
  if success:
    if data != actual:
      f += 1
      print( "\033[31mFAIL:\033[0m RAM[ 0x%08X ]  = "
             "0x%08X (got: 0x%08X)"
             %( address, data, actual ) )
    else:
      p += 1
      print( "\033[32mPASS:\033[0m RAM[ 0x%08X ]  = 0x%08X"
             %( address, data ) )
  else:
    if data != actual:
      p += 1
      print( "\033[32mPASS:\033[0m RAM[ 0x%08X ] != 0x%08X"
             %( address, data ) )
    else:
      f += 1
      print( "\033[31mFAIL:\033[0m RAM[ 0x%08X ] != "
             "0x%08X (got: 0x%08X)"
             %( address, data, actual ) )
  yield Tick()

# Perform an inidividual RAM read unit test.
def ram_read_ut( ram, address, expected ):
  global p, f
  # Set address and 'ren' bit.
  yield ram.addr.eq( address )
  # Wait two ticks, and un-set the 'ren' bit.
  yield Tick()
  yield Tick()
  # Done. Check the 'dout' result after combinational logic settles.
  yield Settle()
  actual = yield ram.dout
  if expected != actual:
    f += 1
    print( "\033[31mFAIL:\033[0m RAM[ 0x%08X ] == "
           "0x%08X (got: 0x%08X)"
           %( address, expected, actual ) )
  else:
    p += 1
    print( "\033[32mPASS:\033[0m RAM[ 0x%08X ] == 0x%08X"
           %( address, expected ) )

# Top-level RAM test method.
def ram_test( ram ):
  global p, f

  # Print a test header.
  print( "--- RAM Tests ---" )

  # Test writing data to RAM.
  yield from ram_write_ut( ram, 0x00, 0x01234567, RAM_DW_32, 1 )
  yield from ram_write_ut( ram, 0x0C, 0x89ABCDEF, RAM_DW_32, 1 )
  # Test reading data back out of RAM.
  yield from ram_read_ut( ram, 0x00, 0x01234567 )
  yield from ram_read_ut( ram, 0x04, 0x00000000 )
  yield from ram_read_ut( ram, 0x0C, 0x89ABCDEF )
  # Test byte-aligned and halfword-aligend reads.
  yield from ram_read_ut( ram, 0x01, 0x00012345 )
  yield from ram_read_ut( ram, 0x02, 0x00000123 )
  yield from ram_read_ut( ram, 0x03, 0x00000001 )
  yield from ram_read_ut( ram, 0x07, 0x00000000 )
  yield from ram_read_ut( ram, 0x0A, 0xCDEF0000 )
  # Test byte-aligned and halfword-aligned writes.
  yield from ram_write_ut( ram, 0x01, 0xDEADBEEF, RAM_DW_32, 1 )
  yield from ram_write_ut( ram, 0x02, 0xDEC0FFEE, RAM_DW_32, 1 )
  yield from ram_write_ut( ram, 0x03, 0xFABFACEE, RAM_DW_32, 1 )
  # Test byte and halfword writes.
  yield from ram_write_ut( ram, 0x00, 0xDEADBEEF, RAM_DW_8, 0 )
  yield from ram_write_ut( ram, 0x10, 0x0000BEEF, RAM_DW_8, 0 )
  yield from ram_write_ut( ram, 0x20, 0x000000EF, RAM_DW_8, 1 )
  yield from ram_write_ut( ram, 0x40, 0xDEADBEEF, RAM_DW_16, 0 )
  yield from ram_write_ut( ram, 0x50, 0x0000BEEF, RAM_DW_16, 1 )
  # Test out-of-bounds write.
  yield from ram_write_ut( ram, ram.size + 5, 0x01234567, RAM_DW_32, 0 )
  # Test reading from the last few bytes of RAM.
  yield from ram_write_ut( ram, ram.size - 4, 0x01234567, RAM_DW_32, 1 )
  yield from ram_read_ut( ram, ram.size - 4, 0x01234567 )
  yield from ram_read_ut( ram, ram.size - 3, 0x00012345 )
  yield from ram_read_ut( ram, ram.size - 2, 0x00000123 )
  yield from ram_read_ut( ram, ram.size - 1, 0x00000001 )
  # Test writing to the end of RAM.
  yield from ram_write_ut( ram, ram.size - 4, 0xABCDEF89, RAM_DW_32, 1 )
  yield from ram_write_ut( ram, ram.size - 3, 0x00000012, RAM_DW_8, 0 )
  yield from ram_read_ut( ram, ram.size - 4, 0xABCD1289 )
  yield from ram_write_ut( ram, ram.size - 4, 0xABCDEF89, RAM_DW_32, 1 )
  yield from ram_write_ut( ram, ram.size - 3, 0x00003412, RAM_DW_16, 0 )
  yield from ram_read_ut( ram, ram.size - 4, 0xAB341289 )
  yield from ram_write_ut( ram, ram.size - 4, 0xABCDEF89, RAM_DW_32, 1 )
  yield from ram_write_ut( ram, ram.size - 1, 0x00000012, RAM_DW_8, 1 )
  yield from ram_read_ut( ram, ram.size - 4, 0x12CDEF89 )
  yield from ram_write_ut( ram, ram.size - 4, 0xABCDEF89, RAM_DW_32, 1 )
  yield from ram_write_ut( ram, ram.size - 3, 0x00234567, RAM_DW_32, 1 )
  yield from ram_read_ut( ram, ram.size - 4, 0x23456789 )

  # Done.
  yield Tick()
  print( "RAM Tests: %d Passed, %d Failed"%( p, f ) )

# 'main' method to run a basic testbench.
if __name__ == "__main__":
  # Instantiate a test RAM module with 128 bytes of data.
  dut = RAM( 32 )

  # Run the RAM tests.
  with Simulator( dut, vcd_file = open( 'ram.vcd', 'w' ) ) as sim:
    def proc():
      yield from ram_test( dut )
    sim.add_clock( 1e-6 )
    sim.add_sync_process( proc )
    sim.run()
