from nmigen import *
from nmigen.back.pysim import *

###############
# ROM module: #
###############

class ROM( Elaboratable ):
  def __init__( self, data ):
    # Address bits to select up to `len( data )` words by byte.
    self.addr = Signal( range( len( data * 4 ) ), reset = 0 )
    # Data word output.
    self.out  = Signal( 32, reset = data[ 0 ] )
    # Data storage.
    self.data = [
      Signal( 32, reset = data[ i ], name = "rom(0x%08X)"%( i * 4 ) )
      for i in range( len( data ) )
    ]
    # Record size.
    self.size = len( data )

  def elaborate( self, platform ):
    # Core ROM module.
    m = Module()

    # Set the 'output' value to 0 if the address is not word-aligned.
    with m.If( ( self.addr & 0b11 ) != 0 ):
      m.d.sync += self.out.eq( 0 )
    # Set the 'output' value to 0 if it is out of bounds.
    with m.Elif( self.addr >= ( self.size * 4 ) ):
      m.d.sync += self.out.eq( 0 )
    # Set the 'output' value to the requested 'data' array index.
    for i in range( self.size ):
      with m.Elif( self.addr == ( i * 4 ) ):
        m.d.sync += self.out.eq( self.data[ i ] )

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
  yield from rom_read_ut( rom, 0x0, ( yield rom.data[ 0 ] ) )
  yield from rom_read_ut( rom, 0x4, ( yield rom.data[ 1 ] ) )
  yield from rom_read_ut( rom, 0x8, ( yield rom.data[ 2 ] ) )
  yield from rom_read_ut( rom, 0xC, ( yield rom.data[ 3 ] ) )
  # Test mis-aligned addresses.
  yield from rom_read_ut( rom, 0x1, 0 )
  yield from rom_read_ut( rom, 0x2, 0 )
  yield from rom_read_ut( rom, 0x3, 0 )

  # Done.
  yield Tick()
  print( "ROM Tests: %d Passed, %d Failed"%( p, f ) )

# 'main' method to run a basic testbench.
if __name__ == "__main__":
  # Instantiate a test ROM module with 16 bytes of data.
  dut = ROM( [ 0x01234567, 0x89ABCDEF, 0x42424242, 0xDEADBEEF ] )

  # Run the ROM tests.
  with Simulator( dut, vcd_file = open( 'rom.vcd', 'w' ) ) as sim:
    def proc():
      yield from rom_test( dut )
    sim.add_clock( 24e-6 )
    sim.add_sync_process( proc )
    sim.run()
