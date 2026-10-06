import urllib.request,ssl,re,html,sys
c=ssl.create_default_context();c.check_hostname=False;c.verify_mode=ssl.CERT_NONE
def get(u):
    b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),context=c,timeout=30).read()
    for e in ('utf-8','gbk'):
        try: return b.decode(e)
        except: pass
    return b.decode('utf-8','ignore')
def text(t):
    s=re.sub(r'(?is)<script.*?</script>|<style.*?</style>','',t)
    s=re.sub(r'(?i)<br\s*/?>|</p>|</div>','\n',s)
    s=html.unescape(re.sub(r'<[^>]+>','',s))
    return re.sub(r'\n\s*\n+','\n',s)
if __name__=='__main__':
    t=get(sys.argv[1]); print(re.search(r'(?s)<title>(.*?)</title>',t).group(1).strip()); s=text(t)
    a=int(sys.argv[2]) if len(sys.argv)>2 else 0; print(s[a:a+int(sys.argv[3]) if len(sys.argv)>3 else a+3000])
