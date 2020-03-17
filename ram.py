from nmigen import *
from nmigen.back.pysim import *

###############
# RAM module: #
###############

class RAM( Elaboratable ):
  def __init__( self, size_words ):
    # Record size.
    self.size = ( size_words * 4 )
    # Address bits to select up to `size_words * 4` bytes.
    self.addr = Signal( range( self.size ), reset = 0 )
    # Data word output.
    self.dout = Signal( 32, reset = 0x00000000 )
    # 'Read Enable' input bit.
    self.ren  = Signal( 1, reset = 0b0 )
    # Data word input.
    self.din  = Signal( 32, reset = 0x00000000 )
    # 'Write Enable' input bit.
    self.wen  = Signal( 1, reset = 0b0 )
    # Data storage, organized as bytes rather than words.
    # Most actual hardware isn't this convenient, but this is
    # simulated RAM, so it's possible to gather data by the byte.
    # An extra word of data is added so that writes can go all
    # the way up to 'size - 1' and still work. I'm not sure why,
    # but 'with m.If( ( i + n ) < self.size ):' doesn't seem to
    # work to prevent out-of-bounds byte writes.
    self.data = [
      Signal( 8, reset = 0x00, name = "ram(0x%08X)"%i )
      for i in range( self.size + 4 )
    ]

  def elaborate( self, platform ):
    # Core RAM module.
    m = Module()

    # Set the 'dout' value if 'ren' is set.
    with m.If( self.ren ):
      # (Return 0 if the address is out of range.)
      with m.If( self.addr >= self.size ):
        m.d.sync += self.dout.eq( 0x00000000 )
      # Read the requested word of RAM. Fill in '0x00' for any bytes
      # which are out of range.
      for i in range( self.size ):
        with m.Elif( self.addr == i ):
          m.d.sync += self.dout.eq(
            ( self.data[ i ] ) |
            ( ( self.data[ i + 1 ] if ( i + 1 ) < self.size else 0x00 ) << 8  ) |
            ( ( self.data[ i + 2 ] if ( i + 2 ) < self.size else 0x00 ) << 16 ) |
            ( ( self.data[ i + 3 ] if ( i + 3 ) < self.size else 0x00 ) << 24 ) )

    # Write the 'din' value if 'wen' is set.
    with m.If( self.wen ):
      # (nop if the write address is out of range.)
      with m.If( self.addr >= self.size ):
        pass
      # Write the requested word of data.
      for i in range( self.size ):
        with m.Elif( self.addr == i ):
          m.d.sync += [
            self.data[ i ].eq( ( self.din & 0x000000FF ) ),
            self.data[ i + 1 ].eq( ( self.din & 0x0000FF00 ) >> 8  ),
            self.data[ i + 2 ].eq( ( self.din & 0x00FF0000 ) >> 16 ),
            self.data[ i + 3 ].eq( ( self.din & 0xFF000000 ) >> 24 )
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
  actual = yield ram.data[ address ]
  actual = actual | ( yield ram.data[ address + 1 ] << 8  )
  actual = actual | ( yield ram.data[ address + 2 ] << 16 )
  actual = actual | ( yield ram.data[ address + 3 ] << 24 )
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
  # Test byte-aligned and halfword-aligend reads.
  yield from ram_read_ut( ram, 0x01, 0x00012345 )
  yield from ram_read_ut( ram, 0x02, 0x00000123 )
  yield from ram_read_ut( ram, 0x03, 0x00000001 )
  yield from ram_read_ut( ram, 0x07, 0x00000000 )
  yield from ram_read_ut( ram, 0x0A, 0xCDEF0000 )
  # Test byte-aligned and halfword-aligned writes.
  yield from ram_write_ut( ram, 0x01, 0xDEADBEEF, 0xDEADBEEF )
  yield from ram_write_ut( ram, 0x02, 0xDEC0FFEE, 0xDEC0FFEE )
  yield from ram_write_ut( ram, 0x03, 0xFABFACEE, 0xFABFACEE )

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
