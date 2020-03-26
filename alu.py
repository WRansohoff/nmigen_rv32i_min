from nmigen import *
from nmigen.back.pysim import *

from isa import *

###############
# ALU module: #
###############

class ALU( Elaboratable ):
  def __init__( self ):
    # 'A' and 'B' data inputs.
    self.a = Signal( shape = Shape( width = 32, signed = True ),
                     reset = 0x00000000 )
    self.b = Signal( shape = Shape( width = 32, signed = True ),
                     reset = 0x00000000 )
    # 'F' function select input.
    self.f = Signal( 4,  reset = 0b0000 )
    # 'Y' data output.
    self.y = Signal( shape = Shape( width = 32, signed = True ),
                     reset = 0x00000000 )
    # 'Start' signal to latch inputs.
    self.start = Signal( reset = 0b0 )
    # 'Reset' signal for clock domains.
    self.clk_rst = Signal( reset = 0b0, reset_less = True )
    # (RISC-V does not have ALU condition flags)

  def elaborate( self, platform ):
    # Core ALU module.
    m = Module()

    # Latched input values for signed and unsigned operations.
    xa   = Signal( shape = Shape( width = 32, signed = True ) )
    xb   = Signal( shape = Shape( width = 32, signed = True ) )
    ua   = Signal( shape = Shape( width = 32, signed = False ) )
    ub   = Signal( shape = Shape( width = 32, signed = False ) )
    fn   = Signal( 4 )

    # Latch input values at rising clock edges if 'start' is set.
    with m.If( self.start ):
      m.d.sync += [
        xa.eq( self.a ),
        xb.eq( self.b ),
        ua.eq( self.a ),
        ub.eq( self.b ),
        fn.eq( self.f ),
      ]

    # Perform ALU computations based on the 'function' bits.
    # Y = A AND B
    with m.If( fn == ALU_AND ):
      m.d.comb += self.y.eq( xa & xb )
    # Y = A  OR B
    with m.Elif( fn == ALU_OR ):
      m.d.comb += self.y.eq( xa | xb )
    # Y = A XOR B
    with m.Elif( fn == ALU_XOR ):
      m.d.comb += self.y.eq( xa ^ xb )
    # Y = A + B
    with m.Elif( fn == ALU_ADD ):
      m.d.comb += self.y.eq( xa + xb )
    # Y = A - B
    with m.Elif( fn == ALU_SUB ):
      m.d.comb += self.y.eq( xa - xb )
    # Y = ( A < B ) (signed)
    with m.Elif( fn == ALU_SLT ):
      m.d.comb += self.y.eq( xa < xb )
    # Y = ( A <  B ) (unsigned)
    with m.Elif( fn == ALU_SLTU ):
      m.d.comb += self.y.eq( ua < ub )
    # Note: Shift operations cannot shift more than XLEN (32) bits.
    # Y = A << B
    with m.Elif( fn == ALU_SLL ):
      m.d.comb += self.y.eq( xa << ( ub & 0x1F ) )
    # Y = A >> B (no sign extend)
    with m.Elif( fn == ALU_SRL ):
      m.d.comb += self.y.eq( ua >> ( ub & 0x1F ) )
    # Y = A >> B (with sign extend)
    with m.Elif( fn == ALU_SRA ):
      m.d.comb += self.y.eq( xa >> ( ub & 0x1F ) )
    # Return 0 after one clock cycle for unrecognized commands.
    with m.Else():
      m.d.comb += self.y.eq( 0x00000000 )

    # End of ALU module definition.
    return m

##################
# ALU testbench: #
##################
# Keep track of test pass / fail rates.
p = 0
f = 0

# Perform an individual ALU unit test.
def alu_ut( alu, a, b, fn, expected ):
  global p, f
  # Set A, B, F.
  yield alu.a.eq( a )
  yield alu.b.eq( b )
  yield alu.f.eq( fn )
  # Pulse 'start' with one intervening clock tick.
  yield alu.start.eq( 1 )
  yield Tick()
  yield alu.start.eq( 0 )
  # Done. Check the result after combinatorial logic settles.
  yield Settle()
  actual = yield alu.y
  if hexs( expected ) != hexs( actual ):
    f += 1
    print( "\033[31mFAIL:\033[0m %s %s %s = %s (got: %s)"
           %( hexs( a ), ALU_STRS[ fn ], hexs( b ),
              hexs( expected ), hexs( actual ) ) )
  else:
    p += 1
    print( "\033[32mPASS:\033[0m %s %s %s = %s"
           %( hexs( a ), ALU_STRS[ fn ],
              hexs( b ), hexs( expected ) ) )

# Top-level ALU test method.
def alu_test( alu ):
  # Let signals settle after reset.
  yield Settle()

  # Print a test header.
  print( "--- ALU Tests ---" )

  # Test the bitwise 'AND' operation.
  print( "AND (&) tests:" )
  yield from alu_ut( alu, 0xCCCCCCCC, 0xCCCC0000, ALU_AND, 0xCCCC0000 )
  yield from alu_ut( alu, 0x00000000, 0x00000000, ALU_AND, 0x00000000 )
  yield from alu_ut( alu, 0xFFFFFFFF, 0xFFFFFFFF, ALU_AND, 0xFFFFFFFF )
  yield from alu_ut( alu, 0x00000000, 0xFFFFFFFF, ALU_AND, 0x00000000 )
  yield from alu_ut( alu, 0xFFFFFFFF, 0x00000000, ALU_AND, 0x00000000 )

  # Test the bitwise 'OR' operation.
  print( "OR  (|) tests:" )
  yield from alu_ut( alu, 0xCCCCCCCC, 0xCCCC0000, ALU_OR, 0xCCCCCCCC )
  yield from alu_ut( alu, 0x00000000, 0x00000000, ALU_OR, 0x00000000 )
  yield from alu_ut( alu, 0xFFFFFFFF, 0xFFFFFFFF, ALU_OR, 0xFFFFFFFF )
  yield from alu_ut( alu, 0x00000000, 0xFFFFFFFF, ALU_OR, 0xFFFFFFFF )
  yield from alu_ut( alu, 0xFFFFFFFF, 0x00000000, ALU_OR, 0xFFFFFFFF )

  # Test the bitwise 'XOR' operation.
  print( "XOR (^) tests:" )
  yield from alu_ut( alu, 0xCCCCCCCC, 0xCCCC0000, ALU_XOR, 0x0000CCCC )
  yield from alu_ut( alu, 0x00000000, 0x00000000, ALU_XOR, 0x00000000 )
  yield from alu_ut( alu, 0xFFFFFFFF, 0xFFFFFFFF, ALU_XOR, 0x00000000 )
  yield from alu_ut( alu, 0x00000000, 0xFFFFFFFF, ALU_XOR, 0xFFFFFFFF )
  yield from alu_ut( alu, 0xFFFFFFFF, 0x00000000, ALU_XOR, 0xFFFFFFFF )

  # Test the addition operation.
  print( "ADD (+) tests:" )
  yield from alu_ut( alu, 0, 0, ALU_ADD, 0 )
  yield from alu_ut( alu, 0, 1, ALU_ADD, 1 )
  yield from alu_ut( alu, 1, 0, ALU_ADD, 1 )
  yield from alu_ut( alu, 0xFFFFFFFF, 1, ALU_ADD, 0 )
  yield from alu_ut( alu, 29, 71, ALU_ADD, 100 )
  yield from alu_ut( alu, 0x80000000, 0x80000000, ALU_ADD, 0 )
  yield from alu_ut( alu, 0x7FFFFFFF, 0x7FFFFFFF, ALU_ADD, 0xFFFFFFFE )

  # Test the signed '<' comparison operation.
  print( "SLT (signed <) tests:" )
  yield from alu_ut( alu, 0, 0, ALU_SLT, 0 )
  yield from alu_ut( alu, 1, 0, ALU_SLT, 0 )
  yield from alu_ut( alu, 0, 1, ALU_SLT, 1 )
  yield from alu_ut( alu, -1, 0, ALU_SLT, 1 )
  yield from alu_ut( alu, -42, -10, ALU_SLT, 1 )
  yield from alu_ut( alu, -10, -42, ALU_SLT, 0 )

  # Test the unsigned '<' comparison operation.
  print( "SLTU (unsigned <) tests:" )
  yield from alu_ut( alu, 0, 0, ALU_SLTU, 0 )
  yield from alu_ut( alu, 1, 0, ALU_SLTU, 0 )
  yield from alu_ut( alu, 0, 1, ALU_SLTU, 1 )
  yield from alu_ut( alu, -1, 0, ALU_SLTU, 0 )
  yield from alu_ut( alu, -42, -10, ALU_SLTU, 1 )
  yield from alu_ut( alu, -10, -42, ALU_SLTU, 0 )
  yield from alu_ut( alu, -42, 42, ALU_SLTU, 0 )

  # Test the shift left operation.
  print ( "SLL (<<) tests:" )
  yield from alu_ut( alu, 0x00000001, 0, ALU_SLL, 0x00000001 )
  yield from alu_ut( alu, 0x00000001, 1, ALU_SLL, 0x00000002 )
  yield from alu_ut( alu, 0x00000001, 4, ALU_SLL, 0x00000010 )
  yield from alu_ut( alu, 0x00000010, 4, ALU_SLL, 0x00000100 )
  yield from alu_ut( alu, 0x80000000, 1, ALU_SLL, 0x00000000 )

  # Test the shift right operation.
  print ( "SRL (>>) tests:" )
  yield from alu_ut( alu, 0x00000001, 0, ALU_SRL, 0x00000001 )
  yield from alu_ut( alu, 0x00000001, 1, ALU_SRL, 0x00000000 )
  yield from alu_ut( alu, 0x00000011, 1, ALU_SRL, 0x00000008 )
  yield from alu_ut( alu, 0x00000010, 1, ALU_SRL, 0x00000008 )
  yield from alu_ut( alu, 0x80000000, 1, ALU_SRL, 0x40000000 )
  yield from alu_ut( alu, 0x80000000, 4, ALU_SRL, 0x08000000 )

  # Test the shift right with sign extension operation.
  print ( "SRA (>> + sign extend) tests:" )
  yield from alu_ut( alu, 0x00000001, 0, ALU_SRA, 0x00000001 )
  yield from alu_ut( alu, 0x00000001, 1, ALU_SRA, 0x00000000 )
  yield from alu_ut( alu, 0x00000011, 1, ALU_SRA, 0x00000008 )
  yield from alu_ut( alu, 0x00000010, 1, ALU_SRA, 0x00000008 )
  yield from alu_ut( alu, 0x80000000, 1, ALU_SRA, 0xC0000000 )
  yield from alu_ut( alu, 0x80000000, 4, ALU_SRA, 0xF8000000 )

  # Done.
  yield Tick()
  print( "ALU Tests: %d Passed, %d Failed"%( p, f ) )

# 'main' method to run a basic testbench.
if __name__ == "__main__":
  # Instantiate an ALU module.
  dut = ALU()

  # Run the tests.
  with Simulator( dut, vcd_file = open( 'alu.vcd', 'w' ) ) as sim:
    def proc():
      yield from alu_test( dut )
    sim.add_clock( 24e-6 )
    sim.add_sync_process( proc )
    sim.run()
