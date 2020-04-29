#include <stdio.h>

typedef unsigned long long u64;
typedef          long long s64;
typedef unsigned int u32;
typedef          int s32;
typedef unsigned short u16;
typedef          short s16;
typedef unsigned char u8;
typedef          char s8;

typedef union {
	u8 bytes[6];
	u16 halves[3];
	struct {
		u8 b1, b2, x, y;
		u16 status;
	};
	struct {
		s8 b1, b2, x, y;
		u16 status;
	} s;
	struct {
		u8 a :1;
		u8 b :1;
		u8 z :1;
		u8 s :1;
		u8 du:1;
		u8 dd:1;
		u8 dl:1;
		u8 dr:1;
		u8 reset:1;
		u8 unused:1;
		u8 l :1;
		u8 r :1;
		u8 cu:1;
		u8 cd:1;
		u8 cl:1;
		u8 cr:1;
		u8 x, y;
		u16 status;
	} buttons;
} raw_input_t;


#define POLLS 8
#define DATA_LEN (45 * ((POLLS) >> 2))
#define COMMAND_LEN ((DATA_LEN) - 5)
#define HUGE_T_SIZE 23 /* ceiling((30 bits * 3 pads * 8 polls) / 32)*/

// Command format:
// 4 poll format: struct { u32 crc32; u8 data[40]; u8 command_id; }
// 8 poll format: struct { u32 crc32; u8 data[85]; u8 command_id; }
typedef union {
	struct {
		u32 crc;
		union {
			u8 bytes[COMMAND_LEN];
			
			// Command 1: Load 81 bytes to given address
			// Command 2: Load up to 80 bytes to given address
			struct {
				u8* address;
				u8  data[COMMAND_LEN - 5];
				u8  length; // Is last data byte when run as command 1
			} cmd01;
			
			// Command 3: Load X counts of byte Y to specified address
			struct {
				u8* address;
				u32 length;
				u8  byte;
				u8  padding[COMMAND_LEN - 9];
			} cmd03;
			
			// Command 4: DMA uncompressed data
			// Command 5: DMA compressed data
			struct {
				u32 vram;
				u32 vrom;
				u32 size;
				u8  padding[COMMAND_LEN - 12];
			} cmd04;
			
			// Command 6: Call command data as code
			//No need for a separate struct--just call `bytes`
			
			// Command 7: Call specified address with up to 4 args
			struct {
				void(*function_pointer)(s32 a0, s32 a1, s32 a2, s32 a3);
				s32 a0;
				s32 a1;
				s32 a2;
				s32 a3;
				u8  padding[COMMAND_LEN - 20];
			} cmd07;
			
		};
		u8 id;
	} command;
	u8 bytes[DATA_LEN];
	u16 halves[DATA_LEN>>1];
} out_data_t;

static out_data_t out_data;
static u8 buf[96];

int main(){
	FILE *f = fopen("test_out.bin", "rb");
	fseek(f, 0, SEEK_END);
	int filelen = ftell(f);
	rewind(f);
	if(filelen != 96){
		printf("Wrong size file\n");
		return 1;
	}
	fread(buf, filelen, 1, f);
	fclose(f);
	
	u8 *b = buf;
	for(u8 i = 0; i < (POLLS); ++i) {
	    raw_input_t* p;
	    
		raw_input_t p_fake[4];
		for(int j=1; j<4; ++j){
			for(int k=0; k<4; ++k){
				p_fake[j].bytes[k] = *b++;
			}
		}
		p = p_fake;
	    
	    // We use halfwords, because two of the raw_input_t objects are 2-byte
	    // aligned and two are 4-byte aligned.
	    u16* data_out = &out_data.halves[6*i];
	    data_out[0] = p[1].halves[0] & 0x3FFF; //LE
	    data_out[1] = p[1].halves[1];
	    data_out[2] = p[2].halves[0] & 0x3FFF;
	    if(i < POLLS-1){
	        data_out[3] = p[2].halves[1];
	        data_out[4] = p[3].halves[0] & 0x3FFF;
	        data_out[5] = p[3].halves[1];
	    }else{
	        u64 temp = p[2].bytes[2];
			temp <<= 8;
			temp |= p[2].bytes[3];
	        temp <<= 8;
	        temp |= p[3].bytes[0];
	        temp <<= 6;
	        temp |= p[3].bytes[1] & 0x3F;
	        temp <<= 8;
	        temp |= p[3].bytes[2];
			temp <<= 8;
			temp |= p[3].bytes[3];
	        //Fill in all the missing 2-bits out of each word
	        for(s32 j=0; j<(DATA_LEN + 3) >> 2; ++j){
	            out_data.bytes[(j<<2)+1] |= (u8)(temp & 3) << 6;
	            temp >>= 2;
	        }
	    }
	}
	
	f = fopen("test_decoded.bin", "wb");
	fwrite(&out_data, 90, 1, f);
	fclose(f);
	
}
