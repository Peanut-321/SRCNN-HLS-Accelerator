// Single-thread scalar Q20.12 CPU baseline. Files contain little-endian int32.
// Same ordered MACs, replicate padding, saturating accumulators and ties-to-even.
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <vector>
std::vector<int32_t> read(const char* p,size_t n){
    std::vector<int32_t> v(n);std::ifstream f(p,std::ios::binary);
    if(!f.read(reinterpret_cast<char*>(v.data()),n*4)||f.peek()!=EOF)throw std::runtime_error("Input size/read error");
    return v;
}
int64_t rounded(int64_t x){
    int64_t q=x/4096,r=x%4096;if(r<0){--q;r+=4096;}
    return q+((r>2048)||(r==2048&&(q%2!=0)));
}
int main(int argc,char**argv){try{
    if(argc!=4)throw std::runtime_error("input.bin model.bin output.bin required");
    auto current=read(argv[1],65025),model=read(argv[2],8129);
    int ins[]={1,64,32},outs[]={64,32,1},ks[]={9,1,5},wo[]={0,5248,7328},bo[]={5184,7296,8128},bits[]={31,37,44};
    auto start=std::chrono::steady_clock::now();
    for(int l=0;l<3;++l){
        std::vector<int32_t> next(outs[l]*65025);
        const int64_t lo=-(int64_t(1)<<(bits[l]-1)),hi=(int64_t(1)<<(bits[l]-1))-1;
        for(int oc=0;oc<outs[l];++oc)for(int y=0;y<255;++y)for(int x=0;x<255;++x){
            int64_t acc=int64_t(model[bo[l]+oc])*4096;
            for(int ic=0;ic<ins[l];++ic)for(int ky=0;ky<ks[l];++ky)for(int kx=0;kx<ks[l];++kx){
                int iy=std::max(0,std::min(254,y+ky-ks[l]/2)),ix=std::max(0,std::min(254,x+kx-ks[l]/2));
                int wi=wo[l]+((oc*ins[l]+ic)*ks[l]+ky)*ks[l]+kx;
                acc+=int64_t(current[ic*65025+iy*255+ix])*model[wi];
                acc=std::max(lo,std::min(hi,acc));
            }
            if(l<2)acc=std::max(int64_t(0),acc);
            next[oc*65025+y*255+x]=int32_t(std::max(int64_t(INT32_MIN),std::min(int64_t(INT32_MAX),rounded(acc))));
        }
        current.swap(next);
    }
    double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
    std::ofstream out(argv[3],std::ios::binary);out.write(reinterpret_cast<const char*>(current.data()),65025*4);
    if(!out)throw std::runtime_error("Output write failed");
    std::cout<<std::setprecision(17)<<seconds<<"\n";
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
