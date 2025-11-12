; Function: deregister_tm_clones
; Address: 0x4003a0 - 0x4003cc

0x4003a0: mov      eax,0x403008
0x4003a5: cmp      rax,0x403008
0x4003ab: je       4003c0 <deregister_tm_clones+0x20>
0x4003ad: mov      eax,0x0
0x4003b2: test     rax,rax
0x4003b5: je       4003c0 <deregister_tm_clones+0x20>
0x4003b7: mov      edi,0x403008
0x4003bc: jmp      rax
0x4003be: xchg     ax,ax
0x4003c0: ret      
0x4003c1: data16   cs nop WORD PTR [rax+rax*1+0x0]
0x4003c8: 00       
0x4003cc: nop      DWORD PTR [rax+0x0]
