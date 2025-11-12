; Function: register_tm_clones
; Address: 0x4003d0 - 0x40040c

0x4003d0: mov      esi,0x403008
0x4003d5: sub      rsi,0x403008
0x4003dc: mov      rax,rsi
0x4003df: shr      rsi,0x3f
0x4003e3: sar      rax,0x3
0x4003e7: add      rsi,rax
0x4003ea: sar      rsi,1
0x4003ed: je       400400 <register_tm_clones+0x30>
0x4003ef: mov      eax,0x0
0x4003f4: test     rax,rax
0x4003f7: je       400400 <register_tm_clones+0x30>
0x4003f9: mov      edi,0x403008
0x4003fe: jmp      rax
0x400400: ret      
0x400401: data16   cs nop WORD PTR [rax+rax*1+0x0]
0x400408: 00       
0x40040c: nop      DWORD PTR [rax+0x0]
