// Standard library includes.
#include <stdint.h>
#include <string.h>
// Device header files
#include "encoding.h"

// Non-standard 'set LED from register' instruction.
#define LED() __asm__( ".word 0x00058076" );

// Pre-boot reset handler: disable interrupts, set the
// stack pointer, then call the 'main' method.
__attribute__( ( naked ) ) void reset_handler( void ) {
  // Disable interrupts.
  clear_csr( mstatus, MSTATUS_MIE );
  // Set the stack pointer.
  __asm__( "la sp, _sp" );
  // Call main(0, 0) in case 'argc' and 'argv' are present.
  __asm__( "li a0, 0\n\t"
           "li a1, 0\n\t"
           "call main" );
}

// Pre-defined memory locations for program initialization.
extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss;
// 'main' method which gets called from the boot code.
int main( void ) {
  // Copy initialized data from .sidata (Flash) to .data (RAM)
  memcpy( &_sdata, &_sidata, ( ( void* )&_edata - ( void* )&_sdata ) );
  // Clear the .bss RAM section.
  memset( &_sbss, 0x00, ( ( void* )&_ebss - ( void* )&_sbss ) );

  // Endlessly increment a register, occasionally toggling
  // the on-board LEDs.
  __asm__( "li a0, 0" );
  __asm__( "li a1, 0" );
  while( 1 ) {
    __asm__( "addi a0, a0, 1" );
    // The non-standard 'LED' instruction sets RGB LEDs based on a
    // register's 3 LSbits. Right-shift the value by several bits
    // so that the transitions are visible.
    __asm__( "srli a1, a0, 12" );
    LED();
  }
  return 0; // lol
}
