"""Deterministic offline merchants. No HTTP, browser, credentials or real purchases."""
import hashlib
import json
from datetime import datetime


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def rupees(minor):
    return f'₹{minor//100:,}' + (f'.{minor%100:02d}' if minor%100 else '')


class SimMerchants:
    def __init__(self):
        self.price_delta=0
        self.sold_out=False
        self.unknown_after_commit=False

    def search(self,domain,slots,occupied=()):
        if self.sold_out:return []
        out=[]
        for variant in range(2):
            seats=[]
            if domain=='retail':
                item=slots['item'];base={'milk':6000,'book':25000,'headphones':59900}.get(item)
                if base is None:return []
                if len(occupied)+int(slots.get('quantity',1))>{'headphones':3,'milk':20,'book':5}[item]:continue
                total=(base+variant*1000+self.price_delta)*int(slots.get('quantity',1))+3000
                title=f'{item.title()} × {slots.get("quantity",1)}';merchant='Sim Mart' if not variant else 'Sim Shop'
                desc='Offline product fixture; delivery fee included. No substitutions.'
            elif domain=='tickets':
                merchant='Sim Cinema Centre' if not variant else 'Sim Cinema Park'
                count=int(slots['partySize']);blocks=[]
                for row in range(10):
                    for start in range(1,14-count):
                        chosen=[f'{chr(65+row)}{n}' for n in range(start,start+count)]
                        # Fixture aisles split seats 6/7; blocked seats never offered.
                        if start<=6<start+count-1 or any(merchant+'|'+s in occupied or s in ('A1','E7') or (s in ('H1','H2') and slots.get('accessibility')!='wheelchair') for s in chosen):continue
                        if slots.get('accessibility')=='wheelchair' and not any(s in ('H1','H2') for s in chosen):continue
                        centre=min(abs(start-7),abs(start+count-1-6)) if slots.get('seatPreference')=='aisle' else abs((start+(count-1)/2)-6.5)
                        score=centre/12+abs(row/9-.65)
                        blocks.append((score,chosen))
                if not blocks:return []
                blocks.sort(key=lambda b:(b[0],b[1]));seats=blocks[min(variant,len(blocks)-1)][1]
                total=(25000+variant*5000+self.price_delta)*count+5000
                title=slots['event'];merchant='Sim Cinema Centre' if not variant else 'Sim Cinema Park'
                desc=f'{slots["area"]}, Fixture Plaza {variant+1}, Screen 1. Seats {", ".join(seats)}: together, centrally ranked around two-thirds back.'
            else:
                total=0;title=f'Table for {slots["partySize"]}';merchant='Sim Table Garden' if not variant else 'Sim Table Central'
                desc=f'{slots["area"]}, Fixture Square {variant+1}. Reservation only; food is not purchased or paid for.'
            preferred=str(slots.get('venue','')).lower()
            if preferred and preferred not in ('choose for me','any','no preference','you choose') and preferred not in merchant.lower():continue
            if domain!='dining' and total>int(slots.get('budgetMinor',0)):continue
            identity=fingerprint([domain,slots,variant])[:24]
            seatmap={'screen':'top','rows':[{'label':chr(65+r),'seats':[{'id':f'{chr(65+r)}{n}','label':str(n),'status':'selected' if f'{chr(65+r)}{n}' in seats else 'taken' if merchant+'|'+f'{chr(65+r)}{n}' in occupied else 'blocked' if f'{chr(65+r)}{n}' in ('A1','E7') else 'accessible' if f'{chr(65+r)}{n}' in ('H1','H2') else 'free'} for n in range(1,13)],'gapsAfter':[5]} for r in range(10)]} if seats else None
            out.append(dict(id=identity,title=title,merchant=merchant,description=desc,totalMinor=total,currency='INR',available=True,**({'seats':seats,'seatMap':seatmap} if seats else {})))
        return sorted(out,key=lambda x:(x['totalMinor'],x['id']))

    def quote(self,domain,slots,offer,clock):
        total=offer['totalMinor'];fees=0 if domain=='dining' else 3000 if domain=='retail' else 5000
        quantity=int(slots.get('quantity' if domain=='retail' else 'partySize',1)) if domain!='dining' else 1
        subtotal=total-fees
        lines=[dict(label=offer['title'],quantity=quantity,unitMinor=subtotal//quantity,totalMinor=subtotal)]
        if fees:lines.append(dict(label='Simulated delivery fee' if domain=='retail' else 'Simulated booking fee',quantity=1,unitMinor=fees,totalMinor=fees))
        selection={**slots,'offerId':offer['id'],'title':offer['title'],'location':offer['description'],**({'seats':offer['seats']} if offer.get('seats') else {})}
        terms='Simulation only. Free simulated cancellation and full simulated refund. No real money or reservation.'
        content=dict(merchant=offer['merchant'],currency='INR',totalMinor=total,lines=lines,terms=terms,selection=selection)
        summary=f'Simulation: {offer["title"]} with {offer["merchant"]}. {offer["description"]} '
        date=datetime.strptime(slots.get('date',slots.get('delivery')),'%Y-%m-%d').strftime('%A, %d %B %Y')
        if domain=='retail':summary+=f'Delivery on {date}. '
        else:
            hour,minute=map(int,slots['time'].split(':'))
            time_label=f'{hour%12 or 12}'+(f':{minute:02}' if minute else '')+(' AM' if hour<12 else ' PM')
            summary+=f'On {date} at {time_label}, India time. '

        summary+=('No charge. Reservation only. ' if domain=='dining' else f'Total {rupees(total)}, including all simulated fees and taxes. ')+terms+' Shall I proceed?'
        return dict(id=fingerprint(content)[:32],revision=1,fingerprint=fingerprint(content),expiresAt=round((clock()+300)*1000),summary=summary,**content)
