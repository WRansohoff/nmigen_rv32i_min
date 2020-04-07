from nmigen import *
from math import ceil, log2
from nmigen.back.pysim import *
from nmigen_soc.memory import *
from nmigen_soc.wishbone import *

from isa import *

###############
# RAM module: #
###############

# Data input width definitions.
RAM_DW_8  = 3
RAM_DW_16 = 2
RAM_DW_32 = 0

class RAM( Elaboratable, Interface ):
  def __init__( self, size_words ):
    # Record size.
    self.size = ( size_words * 4 )
    # Width of data input.
    self.dw   = Signal( 2, reset = 0b00 )
    # 'Write wait-state' bit.
    # Mis-aligned data must be read before re-writing.
    self.wws  = Signal( 1, reset = 0b0 )
    # Data storage.
    self.data = Memory( width = 32, depth = size_words,
      init = ( 0x000000 for i in range( size_words ) ) )
    # Read and write ports.
    self.r = self.data.read_port()
    self.w = self.data.write_port()
    # Initialize wishbone bus interface.
    Interface.__init__( self, addr_width = ceil( log2( self.size + 1 ) ), data_width = 32 )
    self.memory_map = MemoryMap( addr_width = self.addr_width, data_width = self.data_width, alignment = 0 )

  def elaborate( self, platform ):
    # Core RAM module.
    m = Module()
    m.submodules.r = self.r
    m.submodules.w = self.w

    # Reset write data and wait-states when not in use, and
    # disable writes by default.
    m.d.comb += [
      self.w.en.eq( 0 ),
      self.w.data.eq( 0 )
    ]
    m.d.sync += [
      self.wws.eq( 0 ),
      self.ack.eq( 0 )
    ]

    # Set the 'dout' value based on address and RAM data.
    m.d.comb += self.r.addr.eq( self.adr >> 2 )
    # Only set ack if 'cyc' is asserted.
    m.d.sync += self.ack.eq( self.cyc & ( self.stb & ( self.we == 0 ) ) )
    # Word-aligned reads.
    with m.If( ( self.adr & 0b11 ) == 0b00 ):
      m.d.comb += self.dat_r.eq( LITTLE_END( self.r.data ) )
    # Partial reads.
    with m.Else():
      m.d.comb += self.dat_r.eq( LITTLE_END(
        self.r.data << ( ( self.adr & 0b11 ) << 3 ) ) )

    # Write the 'din' value if 'wen' is set.
    with m.If( self.we ):
      # Word-aligned 32-bit writes.
      with m.If( ( ( self.adr & 0b11 ) == 0b00 ) & ( self.dw == RAM_DW_32 ) ):
        m.d.comb += [
          self.w.addr.eq( self.adr >> 2 ),
          self.w.en.eq( self.cyc ),
          self.w.data.eq( LITTLE_END( self.dat_w ) )
        ]
        m.d.sync += self.ack.eq( 1 )
      # Writes requiring wait-states:
      with m.Elif( ( self.wws == 0 ) & ( self.ack == 0 ) ):
        m.d.sync += self.wws.eq( self.wws + 1 )
      with m.Else():
        m.d.sync += [
          self.wws.eq( 0 ),
          self.ack.eq( self.cyc )
        ]
        # Word-aligned partial writes.
        with m.If( ( self.adr & 0b11 ) == 0b00 ):
          m.d.comb += [
            self.w.addr.eq( self.adr >> 2 ),
            self.w.en.eq( self.cyc ),
            self.w.data.eq( self.r.data | LITTLE_END( ( self.dat_w & ( 0xFFFFFFFF >> ( self.dw << 3 ) ) ) ) )
          ]
        # Un-aligned partial writes.
        with m.Else():
          # Assume that read ports hold data from the same addresses.
          m.d.comb += [
            self.w.addr.eq( self.adr >> 2 ),
            self.w.en.eq( self.cyc ),
            self.w.data.eq( ( self.r.data &
              ~( ( ( 0xFFFFFFFF << ( self.dw << 3 ) ) & 0xFFFFFFFF ) >> ( ( self.adr & 0b11 ) << 3 ) ) ) |
              ( LITTLE_END( ( self.dat_w & 0xFFFFFFFF >> ( self.dw << 3 ) ) << ( ( ( self.adr & 0b11 ) << 3 ) ) ) ) ),
          ]

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
  yield ram.adr.eq( address )
  yield ram.dat_w.eq( data )
  yield ram.we.eq( 1 )
  yield ram.dw.eq( dw )
  # Wait two ticks, and un-set the 'wen' bit.
  yield Tick()
  yield Tick()
  yield ram.we.eq( 0 )
  # Done. Check that the 'din' word was successfully set in RAM.
  yield Settle()
  actual = yield ram.dat_r
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
  yield ram.adr.eq( address )
  # Wait two ticks, and un-set the 'ren' bit.
  yield Tick()
  yield Tick()
  # Done. Check the 'dout' result after combinational logic settles.
  yield Settle()
  actual = yield ram.dat_r
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

  # Assert 'cyc' to activate the bus.
  yield ram.cyc.eq( 1 )
  yield Settle()
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
  yield from ram_read_ut( ram, 0x0D, 0x0089ABCD )
  yield from ram_read_ut( ram, 0x0E, 0x000089AB )
  yield from ram_read_ut( ram, 0x0F, 0x00000089 )
  # Test byte-aligned and halfword-aligned writes.
  yield from ram_write_ut( ram, 0x01, 0xDEADBEEF, RAM_DW_32, 0 )
  yield from ram_write_ut( ram, 0x02, 0xDEC0FFEE, RAM_DW_32, 0 )
  yield from ram_write_ut( ram, 0x03, 0xFABFACEE, RAM_DW_32, 0 )
  yield from ram_write_ut( ram, 0x00, 0xAAAAAAAA, RAM_DW_32, 1 )
  yield from ram_write_ut( ram, 0x01, 0xDEADBEEF, RAM_DW_8, 0 )
  yield from ram_read_ut( ram, 0x00, 0xAAAAEFAA )
  yield from ram_write_ut( ram, 0x00, 0xAAAAAAAA, RAM_DW_32, 1 )
  yield from ram_write_ut( ram, 0x02, 0xDEC0FFEE, RAM_DW_16, 0 )
  yield from ram_read_ut( ram, 0x00, 0xFFEEAAAA )
  yield from ram_write_ut( ram, 0x00, 0xAAAAAAAA, RAM_DW_32, 1 )
  yield from ram_write_ut( ram, 0x01, 0xDEC0FFEE, RAM_DW_16, 0 )
  yield from ram_read_ut( ram, 0x00, 0xAAFFEEAA )
  yield from ram_write_ut( ram, 0x00, 0xAAAAAAAA, RAM_DW_32, 1 )
  yield from ram_write_ut( ram, 0x03, 0xDEADBEEF, RAM_DW_8, 0 )
  yield from ram_read_ut( ram, 0x00, 0xEFAAAAAA )
  yield from ram_write_ut( ram, 0x03, 0xFABFACEE, RAM_DW_32, 0 )
  # Test byte and halfword writes.
  yield from ram_write_ut( ram, 0x00, 0x0F0A0B0C, RAM_DW_32, 1 )
  yield from ram_write_ut( ram, 0x00, 0xDEADBEEF, RAM_DW_8, 0 )
  yield from ram_read_ut( ram, 0x00, 0x0F0A0BEF )
  yield from ram_write_ut( ram, 0x10, 0x0000BEEF, RAM_DW_8, 0 )
  yield from ram_read_ut( ram, 0x10, 0x000000EF )
  yield from ram_write_ut( ram, 0x20, 0x000000EF, RAM_DW_8, 1 )
  yield from ram_write_ut( ram, 0x40, 0xDEADBEEF, RAM_DW_16, 0 )
  yield from ram_read_ut( ram, 0x40, 0x0000BEEF )
  yield from ram_write_ut( ram, 0x50, 0x0000BEEF, RAM_DW_16, 1 )
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
  yield from ram_read_ut( ram, ram.size - 3, 0x00234567 )

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
