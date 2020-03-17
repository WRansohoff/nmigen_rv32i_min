from nmigen import *
from nmigen.back.pysim import *

from isa import *

###############
# ROM module: #
###############

class ROM( Elaboratable ):
  def __init__( self, data ):
    # Address bits to select up to `len( data )` words by byte.
    self.addr = Signal( range( len( data ) ), reset = 0 )
    # Data word output.
    self.out  = Signal( 32, reset = (
      ( data[ 0 ] ) |
      ( ( data[ 1 ] if len( data ) > 1 else 0x00 ) << 8  ) |
      ( ( data[ 2 ] if len( data ) > 2 else 0x00 ) << 16 ) |
      ( ( data[ 3 ] if len( data ) > 3 else 0x00 ) << 24 ) ) )
    # Data storage.
    self.data = [
      Signal( 8, reset = data[ i ], name = "rom(0x%08X)"%i )
      for i in range( len( data ) )
    ]
    # Record size.
    self.size = len( data )

  def elaborate( self, platform ):
    # Core ROM module.
    m = Module()

    # Set the 'output' value to 0 if it is out of bounds.
    with m.If( self.addr >= self.size ):
      m.d.sync += self.out.eq( 0 )
    # Set the 'output' value to the requested 'data' array index.
    # If a read would 'spill over' into an out-of-bounds data byte,
    # set that byte to 0x00.
    for i in range( self.size ):
      with m.Elif( self.addr == i ):
        m.d.sync += self.out.eq(
          ( self.data[ i ] ) |
          ( ( self.data[ i + 1 ] if ( i + 1 ) < self.size else 0x00 ) << 8  ) |
          ( ( self.data[ i + 2 ] if ( i + 2 ) < self.size else 0x00 ) << 16 ) |
          ( ( self.data[ i + 3 ] if ( i + 3 ) < self.size else 0x00 ) << 24 ) )

    # End of ROM module definition.
    return m

##################
# ROM testbench: #
##################
# Keep track of test pass / fail rates.
p = 0
f = 0

# Perform an individual ROM unit test.
def rom_read_ut( rom, address, expected ):
  global p, f
  # Set address, and wait one tick.
  yield rom.addr.eq( address )
  yield Tick()
  # Done. Check the result after combinational logic settles.
  yield Settle()
  actual = yield rom.out
  if expected != actual:
    f += 1
    print( "\033[31mFAIL:\033[0m ROM[ 0x%08X ] = 0x%08X (got: 0x%08X)"
           %( address, expected, actual ) )
  else:
    p += 1
    print( "\033[32mPASS:\033[0m ROM[ 0x%08X ] = 0x%08X"
           %( address, expected ) )

# Top-level ROM test method.
def rom_test( rom ):
  global p, f

  # Let signals settle after reset.
  yield Settle()

  # Print a test header.
  print( "--- ROM Tests ---" )

  # Test the ROM's "happy path" (reading valid data).
  yield from rom_read_ut( rom, 0x0, LITTLE_END( 0x01234567 ) )
  yield from rom_read_ut( rom, 0x4, LITTLE_END( 0x89ABCDEF ) )
  yield from rom_read_ut( rom, 0x8, LITTLE_END( 0x42424242 ) )
  yield from rom_read_ut( rom, 0xC, LITTLE_END( 0xDEADBEEF ) )
  # Test byte-aligned and halfword-aligned addresses.
  yield from rom_read_ut( rom, 0x1, LITTLE_END( 0x23456789 ) )
  yield from rom_read_ut( rom, 0x2, LITTLE_END( 0x456789AB ) )
  yield from rom_read_ut( rom, 0x3, LITTLE_END( 0x6789ABCD ) )

  # Done.
  yield Tick()
  print( "ROM Tests: %d Passed, %d Failed"%( p, f ) )

# 'main' method to run a basic testbench.
if __name__ == "__main__":
  # Instantiate a test ROM module with 16 bytes of data.
  dut = ROM( rom_img( [ 0x01234567, 0x89ABCDEF, 0x42424242, 0xDEADBEEF ] ) )

  # Run the ROM tests.
  with Simulator( dut, vcd_file = open( 'rom.vcd', 'w' ) ) as sim:
    def proc():
      yield from rom_test( dut )
    sim.add_clock( 24e-6 )
    sim.add_sync_process( proc )
    sim.run()
