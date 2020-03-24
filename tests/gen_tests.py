# Generate nMigen (or is it pysim?) simulation tests for the
# RV32I RISC-V instruction set, from the 'riscv-tests' ASM files.
# Test files can be found here, under 'isa/rv64ui':
# https://github.com/riscv/riscv-tests
# (The 32-bit ISA uses the 64-bit tests with truncated values)

import os
import subprocess
import sys

od = 'riscv32-unknown-elf-objdump'
test_path = "%s/"%( os.path.dirname( sys.argv[ 0 ] ) )

# Helper method to get raw hex out of an object file memory section
# This basically returns the compiled machine code for one
# of the RISC-V assembly test files.
def get_section_hex( op, sect ):
  hdump = subprocess.run( [ od, '-s', '-j', sect,
                            './%s/rv64ui_tests/%s.o'
                            %( test_path, op ) ],
                          stdout = subprocess.PIPE
                        ).stdout.decode( 'utf-8' )
  hexl = []
  hls = hdump.split( '\n' )[ 4: ]
  for l in hls:
    hl = l.strip()
    while '  ' in hl:
      hl = hl.replace( '  ', ' ' )
    toks = hl.split( ' ' )
    if len( toks ) < 6:
      break
    hexl.append( '0x%s'%toks[ 1 ].upper() )
    hexl.append( '0x%s'%toks[ 2 ].upper() )
    hexl.append( '0x%s'%toks[ 3 ].upper() )
    hexl.append( '0x%s'%toks[ 4 ].upper() )
  return hexl

# Helper method to write a Python file containing a simulated ROM
# test image and testbench condition to verify that it ran correclty.
def write_py_tests( op, hext, hexd ):
  instrs = len( hext )
  opp = op
  while len( opp ) < 5:
    opp = opp + ' '
  py_fn = './%s/test_roms/rv32i_%s.py'%( test_path, op )
  with open( py_fn, 'w' ) as py:
    print( 'Generating %s tests...'%op, end = '' )
    # Write imports and headers.
    py.write( 'from nmigen import *\r\n'
              'from rom import *\r\n'
              '\r\n'
              '###################################\r\n'
              '# rv32ui %s instruction tests: #\r\n'
              '###################################\r\n'
              '\r\n'%opp )
    # Write the ROM image.
    py.write( '# Simulated ROM image:\r\n'
              '%s_rom = ROM( rom_img( ['%op )
    for x in range( len( hext ) ):
      if ( x % 4 ) == 0:
        py.write( '\r\n  ' )
      py.write( '%s'%hext[ x ] )
      if x < ( len( hext ) - 1 ):
        py.write( ', ' )
    py.write( '\r\n] ) )\r\n' )
    # Write the inirialized RAM values.
    py.write( '\r\n# Simulated initialized RAM image:\r\n'
              '# TODO: RAM should eventually be initialized '
              'by the application\r\n'
              '%s_ram = ram_img( ['%op )
    for x in range( len( hexd ) ):
      if ( x % 4 ) == 0:
        py.write( '\r\n  ' )
      py.write( '%s'%hexd[ x ] )
      if x < ( len( hexd ) - 1 ):
        py.write( ', ' )
    py.write( '\r\n] )\r\n' )
    # Run most tests for 2x the number of instructions to account
    # for jumps, except for the 'fence' test which uses 3x because
    # it has a long 'prefetcher test' which counts down from 100.
    num_instrs = ( instrs * 3 ) if 'fence' in op else ( instrs * 2 )
    # Write the 'expected' value for the testbench to check
    # after tests finish.
    py.write( "\r\n# Expected 'pass' register values.\r\n"
              "%s_exp = {\r\n"
              "  %d: [ { 'r': 17, 'e': 93 }, { 'r': 10, 'e': 0 } ],"
              "  'end': %d\r\n}\r\n"%( op, num_instrs, num_instrs ) )
    # Write the test struct.
    py.write( "\r\n# Collected test program definition:\r\n%s_test = "
              "[ '%s tests', 'cpu_%s', %s_rom, %s_ram, %s_exp ]"
              %( op, op.upper(), op, op, op, op ) )
  print( "Done!" )

# Run 'make clean && make' to re-compile the files.
subprocess.run( [ 'make', 'clean' ],
                cwd = './%s/rv64ui_tests/'%test_path )
subprocess.run( [ 'make' ],
                cwd = './%s/rv64ui_tests/'%test_path )
# Process all compiled test files.
for fn in os.listdir( './%s/rv64ui_tests'%test_path ):
  if fn[ -1 ] == 'o':
    op = fn[ :-2 ]
    # Get machine code instructions for the operation's tests.
    hext = get_section_hex( op, '.text' )
    # Get initialized RAM data for the operation's tests.
    hexd = get_section_hex( op, '.data' )
    # Write a Python file with the test ROM image and a simple
    # "expect r7 = 93, r10 = 0 after running all tests" condition.
    write_py_tests( op, hext, hexd )
