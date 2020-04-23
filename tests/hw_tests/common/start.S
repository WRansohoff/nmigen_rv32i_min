/*
 * Main vector table entries.
 * Hold 12 entries for the main vectored exception types.
 */
.global vtable
.type vtable, %object
.section .vector_table,"a",%progbits
vtable:
  J reset_handler
  .align 2
  .word 0
  .word 0
  .word 0
  .word 0
  .word 0
  .word 0
  .word 0
  .word 0
  .word 0
  .word 0
  .word 0
