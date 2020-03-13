from nmigen import *
from nmigen.back.pysim import *

###############
# RAM module: #
###############

class RAM( Elaboratable ):
  def __init__( self, size_words ):
    # Record size.
    self.words = size_words
    # Address bits to select up to `size_words * 4` bytes.
    self.addr = Signal( range( self.words * 4 ), reset = 0 )
    # Data word output.
    self.dout = Signal( 32, reset = 0x00000000 )
    # 'Read Enable' input bit.
    self.ren  = Signal( 1, reset = 0b0 )
    # Data word input.
    self.din  = Signal( 32, reset = 0x00000000 )
    # 'Write Enable' input bit.
    self.wen  = Signal( 1, reset = 0b0 )
    # Data storage.
    self.data = [
      Signal( 32, reset = 0x00000000, name = "ram(0x%08X)"%( i * 4 ) )
      for i in range( self.words )
    ]

  def elaborate( self, platform ):
    # Core RAM module.
    m = Module()

    # Set the 'dout' value if 'ren' is set.
    with m.If( self.ren ):
      # (Return 0 if the address is not word-aligned.)
      with m.If( ( self.addr & 0b11 ) != 0 ):
        m.d.sync += self.dout.eq( 0x00000000 )
      for i in range( self.words ):
        with m.Elif( self.addr == ( i * 4 ) ):
          m.d.sync += self.dout.eq( self.data[ i ] )

    # Write the 'din' value if 'wen' is set.
    with m.If( self.wen ):
      # (nop if the write address is not word-aligned.)
      with m.If( ( self.addr & 0b11 ) != 0 ):
        m.d.sync = m.d.sync
      for i in range( self.words ):
        with m.Elif( self.addr == ( i * 4 ) ):
          m.d.sync += self.data[ i ].eq( self.din )

    # End of RAM module definition.
    return m

##################
# RAM testbench: #
##################
# Keep track of test pass / fail rates.
p = 0
f = 0

# Perform an individual RAM write unit test.
def ram_write_ut( ram, address, data, success ):
  global p, f
  # Set addres, 'din', and 'wen' signals.
  yield ram.addr.eq( address )
  yield ram.din.eq( data )
  yield ram.wen.eq( 1 )
  # Wait one tick, and un-set the 'wen' bit.
  yield Tick()
  yield ram.wen.eq( 0 )
  # Done. Check that the 'din' word was successfully set in RAM.
  yield Settle()
  actual = yield ram.data[ address // 4 ]
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

# Perform an inidividual RAM read unit test.
def ram_read_ut( ram, address, expected ):
  global p, f
  # Set address and 'ren' bit.
  yield ram.addr.eq( address )
  yield ram.ren.eq( 1 )
  # Wait one tick, and un-set the 'ren' bit.
  yield Tick()
  yield ram.ren.eq( 0 )
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
  yield from ram_write_ut( ram, 0x00, 0x01234567, 1 )
  yield from ram_write_ut( ram, 0x0C, 0x89ABCDEF, 1 )
  # Test reading data back out of RAM.
  yield from ram_read_ut( ram, 0x00, 0x01234567 )
  yield from ram_read_ut( ram, 0x04, 0x00000000 )
  yield from ram_read_ut( ram, 0x0C, 0x89ABCDEF )
  # Test mis-aligned writes.
  yield from ram_write_ut( ram, 0x01, 0xDEADBEEF, 0 )
  yield from ram_write_ut( ram, 0x02, 0xDEADBEEF, 0 )
  yield from ram_write_ut( ram, 0x03, 0xDEADBEEF, 0 )
  # Test mis-aligned reads.
  yield from ram_read_ut( ram, 0x01, 0 )
  yield from ram_read_ut( ram, 0x02, 0 )
  yield from ram_read_ut( ram, 0x03, 0 )

  # Done.
  yield Tick()
  print( "RAM Tests: %d Passed, %d Failed"%( p, f ) )

# 'main' method to run a basic testbench.
if __name__ == "__main__":
  # Instantiate a test RAM module with 32 bytes of data.
  dut = RAM( 8 )

  # Run the RAM tests.
  with Simulator( dut, vcd_file = open( 'ram.vcd', 'w' ) ) as sim:
    def proc():
      yield from ram_test( dut )
    sim.add_clock( 24e-6 )
    sim.add_sync_process( proc )
    sim.run()
