# Synthesizes a 34s music bed + SFX synced to the ad's cuts. No external samples.
import numpy as np, wave, sys
SR=44100; D=34.0; N=int(SR*D); out=np.zeros((N,2))
rng=np.random.default_rng(3)
BPM=120; beat=60/BPM
def add(sig,t,gain=1.0,pan=0.0):
    i=int(t*SR); j=min(N,i+len(sig)); s=sig[:j-i]*gain
    out[i:j,0]+=s*(1-pan)/1; out[i:j,1]+=s*(1+pan)/1
def env(n,a=.005,r=.2):
    t=np.arange(n)/SR; return np.minimum(1,t/a)*np.exp(-t/r)
def kick():
    n=int(.35*SR); t=np.arange(n)/SR; f=50+120*np.exp(-t*30)
    return np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-t*9)
def hat(): n=int(.05*SR); return rng.standard_normal(n)*np.exp(-np.arange(n)/SR*90)*.3
def clap():
    n=int(.2*SR); x=rng.standard_normal(n)*np.exp(-np.arange(n)/SR*25); return x*.5
def tone(f,dur,r=.4,kind='saw'):
    n=int(dur*SR); t=np.arange(n)/SR
    w=2*((t*f)%1)-1 if kind=='saw' else np.sin(2*np.pi*f*t)
    return w*env(n,.01,r)
def whoosh(dur=.6,up=True):
    n=int(dur*SR); x=rng.standard_normal(n); t=np.linspace(0,1,n)
    e=(t if up else 1-t)**2*np.sin(np.pi*t)
    # crude lowpass sweep via moving average of varying width
    y=np.convolve(x,np.ones(8)/8,'same')
    return y*e*.6
def hit():
    n=int(1.2*SR); t=np.arange(n)/SR
    return (np.sin(2*np.pi*55*t)*.9+rng.standard_normal(n)*.25*np.exp(-t*12))*np.exp(-t*3)
def lp(x,k=12): return np.convolve(x,np.ones(k)/k,'same')

# chords (Am - F - C - G), minor driving feel
roots=[110.0,87.31,130.81,98.0]
bar=4*beat
# Section intensity: intro sparse (0-4.2), tension (4.2-9.6), drop (9.6-28.4), outro (28.4-34)
t=0.0; b=0
while t<D:
    sec = 0 if t<4.2 else 1 if t<9.6 else 2 if t<28.4 else 3
    if sec>=1 and sec!=3 or (sec==3 and t<31.5): add(kick(),t,.9 if sec==2 else .55)
    if sec==2:
        add(hat(),t+beat/2,.6,.3); add(hat(),t+beat/4*3,.3,-.3)
        if b%2==1: add(clap(),t,.5)
    r=roots[(int(t/bar))%4]
    if sec>=1:
        add(lp(tone(r/2,beat*.9,.25)),t,.35)  # bass
    if sec in (0,2,3):
        for k,m in enumerate([1,1.189,1.498]):  # minor triad pad stab
            add(lp(tone(r*2*m,beat*.8,.3),20),t,.06,(k-1)*.4)
    t+=beat; b+=1

# riser into drop and SFX on cuts
add(whoosh(1.4,True),9.6-1.4,.8)
for c in [4.2,7.0,14.6,19.4,23.0]: add(whoosh(.45,False),c-.05,.6)
for c in [9.6,28.4]: add(hit(),c,.8)
# sad "bonk" when 2,147 views lands
add(tone(220,.4,.25,'sin')+tone(207,.4,.25,'sin'),5.6,.4)
# ticks during counters
for i in range(40): add(hat(),4.4+i*0.03,.15)
for i in range(60): add(hat(),14.8+i*0.062,.12)
# step highlights
for i in range(3): add(tone(880*(1.26**i),.25,.12,'sin'),24.8+i,.25)
# end chime
for k,f in enumerate([523.25,659.25,783.99,1046.5]): add(tone(f,1.5,.6,'sin'),30.4+k*.07,.15)

# fade out and normalize
fo=int(2*SR); out[-fo:]*=np.linspace(1,0,fo)[:,None]
out/=np.abs(out).max()*1.12
pcm=(out*32767).astype(np.int16)
with wave.open(sys.argv[1],'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
