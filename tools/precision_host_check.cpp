// Offline scalar ap_fixed check for the precision study, NOT a new HLS top.
// Compile against vendor-compatible ap_fixed headers; no DUT edits are needed.
#include <ap_fixed.h>
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

constexpr int magnitude_bits(std::uint64_t value) {
    int bits=0;
    while(value) { ++bits; value >>= 1; }
    return bits;
}
template<int F> struct Sizing {
    static constexpr std::uint64_t scale=1ULL<<F;
    static constexpr std::uint64_t high=(1ULL<<31)-1;
    static constexpr std::uint64_t bound1=82*scale*scale;
    static constexpr std::uint64_t incoming1=(bound1+scale-1)/scale < high ? (bound1+scale-1)/scale : high;
    static constexpr std::uint64_t bound2=64*incoming1*scale+scale*scale;
    static constexpr std::uint64_t incoming2=(bound2+scale-1)/scale < high ? (bound2+scale-1)/scale : high;
    static constexpr std::uint64_t bound3=800*incoming2*scale+scale*scale;
    static constexpr int w1=1+magnitude_bits(bound1), w2=1+magnitude_bits(bound2), w3=1+magnitude_bits(bound3);
};

std::vector<float> read_floats(const std::string& path, int count=-1) {
    std::ifstream file(path,std::ios::binary|std::ios::ate);
    const auto bytes=file.tellg();
    if(!file || bytes<0 || bytes%sizeof(float)!=0 || (count>=0 && bytes!=count*int(sizeof(float))))
        throw std::runtime_error("invalid float file: "+path);
    std::vector<float> values(static_cast<std::size_t>(bytes)/sizeof(float));
    file.seekg(0); file.read(reinterpret_cast<char*>(values.data()),bytes);
    if(!file) throw std::runtime_error("float read failed");
    return values;
}
template<class Data> void write_codes(const std::string& path,const std::vector<Data>& values) {
    std::ofstream file(path,std::ios::binary);
    for(const auto& value:values) {
        const std::uint32_t bits=value.range(31,0).to_uint();
        file.write(reinterpret_cast<const char*>(&bits),sizeof(bits));
    }
    if(!file) throw std::runtime_error("output write failed");
}
template<class Data,int W,int F>
std::vector<Data> convolution(const std::vector<Data>& input,const std::vector<Data>& model,
                             int height,int width,int inputs,int outputs,int kernel,
                             int weight_offset,int bias_offset,bool relu) {
    using Acc=ap_fixed<W,W-2*F,AP_TRN,AP_SAT>;
    std::vector<Data> result(outputs*height*width);
    for(int oc=0;oc<outputs;++oc) for(int r=0;r<height;++r) for(int c=0;c<width;++c) {
        Acc sum=model[bias_offset+oc];
        for(int ic=0;ic<inputs;++ic) for(int kr=0;kr<kernel;++kr) for(int kc=0;kc<kernel;++kc) {
            const int ir=std::max(0,std::min(height-1,r+kr-kernel/2));
            const int ix=std::max(0,std::min(width-1,c+kc-kernel/2));
            sum += input[(ic*height+ir)*width+ix]*model[weight_offset+((oc*inputs+ic)*kernel+kr)*kernel+kc];
        }
        if(relu && sum<0) sum=0;
        result[(oc*height+r)*width+c]=Data(sum);
    }
    return result;
}
template<int F> void run(int argc,char** argv,bool quantize_only) {
    using Data=ap_fixed<32,32-F,AP_RND_CONV,AP_SAT>;
    if(quantize_only) {
        const auto input=read_floats(argv[3]);
        std::vector<Data> codes(input.begin(),input.end());
        write_codes(argv[4],codes);
        std::cout<<"PASS ap_fixed quantization F="<<F<<" values="<<codes.size()<<"\n";
        return;
    }
    const int height=std::stoi(argv[2]),width=std::stoi(argv[3]);
    if(height<1 || width<1 || height>255 || width>255) throw std::runtime_error("invalid H/W");
    const auto image=read_floats(argv[4],height*width),parameters=read_floats(argv[5],8129);
    const std::vector<Data> input(image.begin(),image.end()),model(parameters.begin(),parameters.end());
    const auto conv1=convolution<Data,Sizing<F>::w1,F>(input,model,height,width,1,64,9,0,5184,true);
    const auto conv2=convolution<Data,Sizing<F>::w2,F>(conv1,model,height,width,64,32,1,5248,7296,true);
    const auto conv3=convolution<Data,Sizing<F>::w3,F>(conv2,model,height,width,32,1,5,7328,8128,false);
    write_codes(std::string(argv[6])+".conv1.bin",conv1);
    write_codes(std::string(argv[6])+".conv2.bin",conv2);
    write_codes(std::string(argv[6])+".conv3.bin",conv3);
    std::cout<<"PASS ap_fixed scalar F="<<F<<" "<<height<<"x"<<width
             <<" acc="<<Sizing<F>::w1<<"/"<<Sizing<F>::w2<<"/"<<Sizing<F>::w3<<"\n";
}
int main(int argc,char** argv) {
    try {
        const bool quantize_only=argc>1 && std::string(argv[1])=="--quantize";
        if((quantize_only && argc!=5) || (!quantize_only && argc!=7))
            throw std::runtime_error("F H W input_f32 model_f32 output_prefix; or --quantize F input_f32 output_raw");
        const int fraction=std::stoi(argv[quantize_only?2:1]);
        switch(fraction) {
            case 8: run<8>(argc,argv,quantize_only); break;
            case 10: run<10>(argc,argv,quantize_only); break;
            case 12: run<12>(argc,argv,quantize_only); break;
            case 14: run<14>(argc,argv,quantize_only); break;
            case 16: run<16>(argc,argv,quantize_only); break;
            case 18: run<18>(argc,argv,quantize_only); break;
            case 20: run<20>(argc,argv,quantize_only); break;
            default: throw std::runtime_error("supported F: 8,10,12,14,16,18,20");
        }
    } catch(const std::exception& error) { std::cerr<<error.what()<<"\n"; return 1; }
}
