from nmigen import *
from math import ceil, log2
from nmigen.back.pysim import *
from nmigen_soc.memory import *
from nmigen_soc.wishbone import *
from nmigen_boards.resources import *

###########################
# SPI Flash "ROM" module: #
# TODO: error-checking :/ #
###########################

# (Dummy SPI resources for simulated tests)
class DummyPin():
  def __init__( self ):
    self.o = Signal()
    self.i = Signal()
class DummySPI():
  def __init__( self ):
    self.cs   = DummyPin()
    self.clk  = DummyPin()
    self.mosi = DummyPin()
    self.miso = DummyPin()

# Core SPI Flash "ROM" module.
class SPIROM( Elaboratable, Interface ):
  def __init__( self, dat_start, dat_end ):
    # Starting address in the Flash chip. This probably won't
    # be zero, because many FPGA boards use their external SPI
    # Flash to store the bitstream which configures the chip.
    self.dstart = dat_start
    # Last accessible address in the flash chip.
    self.dend = dat_end
    # Length of accessible data.
    self.dlen = ( dat_end - dat_start ) + 1
    # SPI Flash address command.
    self.spio = Signal( 32, reset = 0x00000003 )
    # Data counter.
    self.dc = Signal( 6, reset = 0b000000 )

    # Initialize Wishbone bus interface.
    Interface.__init__( self, addr_width = ceil( log2( self.dlen + 1 ) ), data_width = 32 )
    self.memory_map = MemoryMap( addr_width = self.addr_width, data_width = self.data_width, alignment = 0 )

  def elaborate( self, platform ):
    m = Module()

    # Retrieve SPI Flash resources.
    # TODO: take this as an arg? It can only be 'borrowed' once.
    if platform is not None:
      self.spi = platform.request( 'spi_flash' )
    else:
      self.spi = DummySPI()

    # Clock rests at 0.
    m.d.sync += self.spi.clk.o.eq( 0 )
    # SPI Flash can only address 24 bits.
    m.d.comb += self.spio.eq( ( 0x03 | ( ( self.adr + self.dstart ) << 8 ) )[ :32 ] )

    # Use a state machine for Flash access.
    # "Mode 0" SPI is very simple:
    # - Device is active when CS is low, inactive otherwise.
    # - Clock goes low, both sides write their bit if necessary.
    # - Clock goes high, both sides read their bit if necessary.
    # - Repeat ad nauseum.
    with m.FSM() as fsm:
      # 'Waiting' state:
      with m.State( "SPI_WAITING" ):
        m.d.sync += [
          self.ack.eq( self.ack & self.stb ),
          self.spi.cs.o.eq( 1 )
        ]
        with m.If( ( self.stb == 1 ) & ( self.ack == 0 ) ):
          m.d.sync += [
            self.spi.cs.o.eq( 0 ),
            self.spi.mosi.o.eq( self.spio[ 0 ] ),
            self.ack.eq( 0 ),
            self.dc.eq( 0 )
          ]
          m.next = "SPI_TX"
      # 'Send address' state:
      with m.State( "SPI_TX" ):
        m.d.sync += self.dc.eq( self.dc + 1 )
        with m.If( self.dc[ 0 ] == 0 ):
          m.d.sync += self.spi.clk.o.eq( 1 )
          m.next = "SPI_TX"
        with m.Else():
          m.d.sync += [
            self.spi.clk.o.eq( 0 ),
            self.spi.mosi.o.eq( self.spio >> ( self.dc[ 1: ] ) )
          ]
          with m.If( self.dc == 0b111111 ):
            m.d.sync += [
              self.dc.eq( 0 ),
              self.dat_r.eq( 0 )
            ]
            m.next = "SPI_RX"
          with m.Else():
            m.next = "SPI_TX"
      # 'Receive data' state:
      with m.State( "SPI_RX" ):
        m.d.sync += self.dc.eq( self.dc + 1 )
        with m.If( self.dc[ 0 ] == 0 ):
          m.d.sync += self.spi.clk.o.eq( 1 )
          m.next = "SPI_RX"
        with m.Else():
          m.d.sync += [
            self.spi.clk.o.eq( 0 ),
            self.dat_r.eq( self.dat_r | ( self.spi.miso.i << ( self.dc[ 1: ] ) ) )
          ]
          with m.If( self.dc == 0b111111 ):
            m.d.sync += [
              self.ack.eq( 1 ),
              self.spi.cs.o.eq( 1 )
            ]
            m.next = "SPI_WAITING"
          with m.Else():
            m.next = "SPI_RX"

    return m

##############################
# SPI Flash "ROM" testbench: #
##############################
# Keep track of test pass / fail rates.
p = 0
f = 0

# Helper method to record test pass/fails.
def spi_rom_ut( name, actual, expected ):
  global p, f
  if expected != actual:
    f += 1
    print( "\033[31mFAIL:\033[0m %s (0x%08X != 0x%08X)"
           %( name, actual, expected ) )
  else:
    p += 1
    print( "\033[32mPASS:\033[0m %s (0x%08X == 0x%08X)"
           %( name, actual, expected ) )

# Helper method to test reading a byte of SPI data.
def spi_read_word( srom, virt_addr, phys_addr, simword, end_wait ):
  # Set 'address'.
  yield srom.adr.eq( virt_addr )
  # Set 'strobe' and 'cycle' to request a new read.
  yield srom.stb.eq( 1 )
  yield srom.cyc.eq( 1 )
  # Wait two ticks; CS pin should then be low.
  yield Tick()
  yield Settle()
  csa = yield srom.spi.cs.o
  spcmd = yield srom.spio
  spi_rom_ut( "CS Low", csa, 0 )
  spi_rom_ut( "SPI Read Cmd Value", spcmd, ( phys_addr << 8 ) | 0x03 )
  yield Tick()
  # Then the 32-bit read command is sent; two ticks per bit.
  for i in range( 32 ):
    yield Tick()
    yield Settle()
    dout = yield srom.spi.mosi.o
    spi_rom_ut( "SPI Read Cmd  [%d]"%i, dout, ( spcmd >> i ) & 0b1 )
    yield Tick()
  # The following 32 bits should return the word. Simulate
  # the requested word arriving on the MISO pin, LSbit first.
  for i in range( 32 ):
    yield srom.spi.miso.i.eq( ( simword >> i ) & 0b1 )
    yield Tick()
    yield Settle()
    progress = yield srom.dat_r
    spi_rom_ut( "SPI Read Word [%d]"%i, progress, ( simword & ( 0xFFFFFFFF >> ( 31 - i ) ) ) )
    yield Tick()
  yield Settle()
  csa = yield srom.spi.cs.o
  spi_rom_ut( "CS High (Waiting)", csa, 1 )
  # Done; reset 'strobe' and 'cycle' after N ticks.
  for i in range( end_wait ):
    yield Tick()
  yield srom.stb.eq( 0 )
  yield srom.cyc.eq( 0 )
  yield Tick()
  yield Settle()

# Top-level SPI ROM test method.
def spi_rom_tests( srom ):
  global p, f

  # Let signals settle after reset.
  yield Tick()
  yield Settle()

  # Print a test header.
  print( "--- SPI Flash 'ROM' Tests ---" )

  # Test basic behavior by reading a few consecutive words.
  yield from spi_read_word( srom, 0x0A, 0x1A, 0x89ABCDEF, 0 )
  yield from spi_read_word( srom, 0x0B, 0x1B, 0x0C0FFEE0, 4 )
  for i in range( 4 ):
    yield Tick()
    yield Settle()
    csa = yield srom.spi.cs.o
    spi_rom_ut( "CS High (Waiting)", csa, 1 )
  yield from spi_read_word( srom, 0x0F, 0x1F, 0xDEADFACE, 1 )
  yield from spi_read_word( srom, 0x00, 0x10, 0xABACADAB, 1 )

  # Done.
  yield Tick()
  print( "SPI 'ROM' Tests: %d Passed, %d Failed"%( p, f ) )

# 'main' method to run a basic testbench.
if __name__ == "__main__":
  # Instantiate a test SPI ROM module.
  dut = SPIROM( 0x10, 0x100 )

  # Run the SPI ROM tests.
  with Simulator( dut, vcd_file = open( 'spi_rom.vcd', 'w' ) ) as sim:
    def proc():
      yield from spi_rom_tests( dut )
    sim.add_clock( 1e-6 )
    sim.add_sync_process( proc )
    sim.run()
