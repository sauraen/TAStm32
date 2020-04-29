/*
 * z64_tc.h
 *
 * Zelda 64 Total Control data interface
 */

#ifndef Z64_TC_H_
#define Z64_TC_H_

#include "TASRun.h"

extern void TC_Reset(TASRun *tasrun);
extern uint8_t TC_Validate_NewCmd(TASRun *tasrun);
extern uint8_t TC_RecCmdByte(TASRun *tasrun, uint8_t input);

extern void TC_Got_Identity(TASRun *tasrun, uint8_t player);
extern void TC_Got_Reset(TASRun *tasrun, uint8_t player);
extern void TC_Poll(TASRun *tasrun, uint8_t player, uint8_t *result, uint8_t *resultlen);
extern void TC_MempakRead(TASRun *tasrun, uint8_t player, int8_t cmd_bytes, uint8_t *result, uint8_t *resultlen);
extern void TC_MempakWrite(TASRun *tasrun, uint8_t player, int8_t cmd_bytes, uint8_t *result, uint8_t *resultlen);

#endif /* Z64_TC_H_ */
