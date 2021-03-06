from nmigen import *
from math import ceil, log2
from nmigen.back.pysim import *
from nmigen_soc.memory import *
from nmigen_soc.wishbone import *

from rom import *
from isa import *

###########################
# Multiplexed ROM module: #
###########################

class MUXROM( Elaboratable ):
  def __init__( self, roms ):
    # Collect max / mins from available ROMs.
    self.max_addr_len = 1
    for rom in roms:
      if ( rom.size * 4 ) > self.max_addr_len:
        self.max_addr_len = rom.size * 4
    # 'Select' signal to choose which ROM module to address.
    self.select = Signal( range( len( roms ) ), reset = 0 )
    # Rom storage.
    self.roms = roms
    # Number of ROMs.
    self.rlen = len( roms )
    # Initialize Wishbone bus arbiter.
    self.arb = Arbiter( addr_width = ceil( log2( self.max_addr_len + 1 ) ),
                        data_width = 32 )
    self.arb.bus.memory_map = MemoryMap(
      addr_width = self.arb.bus.addr_width,
      data_width = self.arb.bus.data_width,
      alignment = 0 )

  def new_bus( self ):
    # Initialize a new Wishbone bus interface.
    bus = Interface( addr_width = self.arb.bus.addr_width,
                     data_width = self.arb.bus.data_width )
    bus.memory_map = MemoryMap( addr_width = bus.addr_width,
                                data_width = bus.data_width,
                                alignment = 0 )
    self.arb.add( bus )
    return bus

  def elaborate( self, platform ):
    # Module object.
    m = Module()
    m.submodules.arb = self.arb
    # Register each ROM submodule.
    for i in range( self.rlen ):
      m.submodules[ "rom_%d"%i ] = self.roms[ i ]

    # Return 0 for an out-of-range 'select' signal.
    with m.If( self.select >= self.rlen ):
      m.d.comb += self.arb.bus.dat_r.eq( 0x00000000 )
    # Forward the bus signals to the appropriate ROM.
    with m.Else():
      m.d.comb += [
        self.roms[ self.select ].arb.bus.adr.eq( self.arb.bus.adr ),
        self.arb.bus.ack.eq( self.roms[ self.select ].arb.bus.ack ),
        self.roms[ self.select ].arb.bus.stb.eq( self.arb.bus.stb ),
        self.roms[ self.select ].arb.bus.cyc.eq( self.arb.bus.cyc ),
        self.arb.bus.dat_r.eq( self.roms[ self.select ].arb.bus.dat_r )
      ]

    # End of module definition.
    return m

##############################
# Multiplexed ROM testbench: #
##############################
# Keep track of test pass / fail rates.
p = 0
f = 0

# Perform an individual unit test.
def muxrom_read_ut( mrom, select, address, expected ):
  global p, f
  # Set select and address, then wait three ticks.
  yield mrom.select.eq( select )
  yield mrom.arb.bus.adr.eq( address )
  yield Tick()
  yield Tick()
  yield Tick()
  # Done. Check the result after the combinational logic settles.
  yield Settle()
  actual = yield mrom.arb.bus.dat_r
  if expected != actual:
    f += 1
    print( "\033[31mFAIL:\033[0m ROM[ 0x%08X ] = 0x%08X (got: 0x%08X)"
           %( address, expected, actual ) )
  else:
    p += 1
    print( "\033[32mPASS:\033[0m ROM[ 0x%08X ] = 0x%08X"
           %( address, expected ) )

# Top-level multiplexed ROM test method.
def muxrom_test( mrom ):
  global p, f

  # Let signals settle after reset.
  yield Settle()

  # Print a test header.
  print( "--- Multiplexed ROM Tests ---" )

  # Assert 'cyc' to activate the bus.
  yield mrom.arb.bus.cyc.eq( 1 )
  # Test reading from the first ROM.
  yield from muxrom_read_ut( mrom, 0, 0x0,
    LITTLE_END( ( yield mrom.roms[ 0 ].data[ 0 ] ) ) )
  yield from muxrom_read_ut( mrom, 0, 0x4,
    LITTLE_END( ( yield mrom.roms[ 0 ].data[ 1 ] ) ) )
  # Test reading from the second ROM.
  yield from muxrom_read_ut( mrom, 1, 0x8,
    LITTLE_END( ( yield mrom.roms[ 1 ].data[ 2 ] ) ) )
  yield from muxrom_read_ut( mrom, 1, 0xC,
    LITTLE_END( ( yield mrom.roms[ 1 ].data[ 3 ] ) ) )
  # Test reading from the third ROM.
  yield from muxrom_read_ut( mrom, 2, 0x0,
    LITTLE_END( ( yield mrom.roms[ 2 ].data[ 0 ] ) ) )
  yield from muxrom_read_ut( mrom, 2, 0x4,
    LITTLE_END( ( yield mrom.roms[ 2 ].data[ 1 ] ) ) )
  # Test byte-aligned and halfword-aligned reads.
  yield from muxrom_read_ut( mrom, 0, 0x1, 0x00674523 )
  yield from muxrom_read_ut( mrom, 1, 0x2, 0x00006745 )
  # Test reading from an out-of-range ROM.
  yield from muxrom_read_ut( mrom, 3, 0x0, 0x00000000 )

  # Done.
  yield Tick()
  print( "Mux ROM Tests: %d Passed, %d Failed"%( p, f ) )

# 'main' method to run a basic testbench.
if __name__ == "__main__":
  # Instantiate a test module with 3 ROMs.
  dut = MUXROM( Array( [
           ROM( [ 0x01234567, 0x89ABCDEF, 0x42424242, 0xDEC0FFEE ] ),
           ROM( [ 0x01234567, 0x89ABCDEF, 0x42424242, 0xBEEFFACE ] ),
           ROM( [ 0x01234567, 0x89ABCDEF ] ) ] ) )

  # Run the multiplexed ROM tests.
  with Simulator( dut, vcd_file = open( 'mux_rom.vcd', 'w' ) ) as sim:
    def proc():
      yield from muxrom_test( dut )
    sim.add_clock( 1e-6 )
    sim.add_sync_process( proc )
    sim.run()
