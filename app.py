import sqlite3
from datetime import date
import pandas as pd
import streamlit as st

st.set_page_config(page_title='Lampone Gestión',page_icon='🍓',layout='wide')
DB='lampone.db'
def conn():
    c=sqlite3.connect(DB)
    c.execute('PRAGMA foreign_keys=ON')
    return c

def init():
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,unit TEXT NOT NULL,stock REAL NOT NULL DEFAULT 0,min_stock REAL NOT NULL DEFAULT 0,cost REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS recipes(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,yield_qty INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS recipe_lines(recipe_id INTEGER,item_id INTEGER,qty REAL NOT NULL,PRIMARY KEY(recipe_id,item_id),FOREIGN KEY(recipe_id) REFERENCES recipes(id),FOREIGN KEY(item_id) REFERENCES items(id));
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,customer TEXT,recipe_id INTEGER,batches INTEGER,process_date TEXT,delivery_date TEXT,price REAL,status TEXT DEFAULT 'Pendiente');
        CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY,created_at TEXT DEFAULT CURRENT_TIMESTAMP,item_id INTEGER,qty REAL,type TEXT,reference TEXT,unit_cost REAL);
        ''')
        if not c.execute('SELECT 1 FROM items LIMIT 1').fetchone():
            c.executemany('INSERT INTO items(name,unit,stock,min_stock,cost) VALUES(?,?,?,?,?)',[
                ('Harina','g',5000,1000,1.5),('Azúcar','g',3000,800,1.2),('Huevos','unidad',60,12,120),('Mantequilla','g',3000,500,5),('Chocolate','g',2000,400,8),('Caja de galletas','unidad',30,10,350),('Etiqueta','unidad',50,15,60)])
        if not c.execute('SELECT 1 FROM recipes LIMIT 1').fetchone():
            rid=c.execute('INSERT INTO recipes(name,yield_qty) VALUES(?,?)',('Galletas de chocolate',20)).lastrowid
            for name,qty in [('Harina',500),('Azúcar',200),('Huevos',3),('Mantequilla',250),('Chocolate',150),('Caja de galletas',3),('Etiqueta',3)]:
                iid=c.execute('SELECT id FROM items WHERE name=?',(name,)).fetchone()[0]
                c.execute('INSERT INTO recipe_lines VALUES(?,?,?)',(rid,iid,qty))
def query(sql,args=()):
    with conn() as c:return pd.read_sql_query(sql,c,params=args)
def recipes():return query('SELECT * FROM recipes')
def items():return query('SELECT * FROM items')
def lines(rid):return query('SELECT i.id,i.name,i.unit,i.stock,i.cost,rl.qty FROM recipe_lines rl JOIN items i ON i.id=rl.item_id WHERE rl.recipe_id=?',(rid,))
def needs(rid,batches):
    l=lines(rid);l['needed']=l.qty*batches;return l

def reserved(item_id,exclude_order=None):
    sql='''SELECT COALESCE(SUM(rl.qty*o.batches),0) FROM orders o JOIN recipe_lines rl ON rl.recipe_id=o.recipe_id WHERE o.status='Pendiente' AND rl.item_id=?'''
    args=[int(item_id)]
    if exclude_order is not None:sql+=' AND o.id<>?';args.append(int(exclude_order))
    with conn() as c:return c.execute(sql,args).fetchone()[0]

def cost(rid,batches):return float((needs(rid,batches).qty*needs(rid,batches).cost).sum())

init()
st.title('🍓 Lampone | Gestión')
st.caption('Prototipo con datos de demostración. La base SQLite se guarda en el entorno de Replit; para uso real se necesita almacenamiento persistente y respaldos.')
page=st.sidebar.radio('Menú',['Panel','Recetas','Inventario','Pedidos','Producción','Movimientos y costos'])
rs=recipes();it=items()
rmap=dict(zip(rs.name,rs.id));imap=dict(zip(it.name,it.id))
if page=='Panel':
    orders=query("SELECT COUNT(*) n FROM orders WHERE status='Pendiente'").iloc[0]['n']
    value=float((it.stock*it.cost).sum());alerts=sum(row.stock-reserved(row.id)<=row.min_stock for row in it.itertuples())
    a,b,c=st.columns(3);a.metric('Valor de inventario',f'₡{value:,.0f}');b.metric('Pedidos pendientes',int(orders));c.metric('Insumos por revisar',int(alerts))
    st.info('Los pedidos reservan materiales. La producción confirmada descuenta las existencias físicas.')
elif page=='Recetas':
    st.subheader('Recetas guardadas')
    for r in rs.itertuples():
        with st.expander(f'{r.name} · {r.yield_qty} unidades por tanda · ₡{cost(r.id,1):,.0f}'):
            st.dataframe(lines(r.id)[['name','qty','unit','cost']],hide_index=True)
    st.subheader('Crear receta')
    with st.form('recipe'):
        name=st.text_input('Nombre de receta');yield_qty=st.number_input('Unidades obtenidas por tanda',1,100000,20)
        st.caption('Elegí ingredientes y empaques. Se guardan sus cantidades por tanda.')
        quantities={}
        for i in it.itertuples():
            quantities[i.id]=st.number_input(f'{i.name} ({i.unit})',min_value=0.0,value=0.0,step=1.0,key=f'ingredient_{i.id}')
        submit=st.form_submit_button('Guardar receta')
    if submit:
        if not name.strip() or not any(quantities.values()):st.error('Indicá un nombre y al menos un ingrediente.')
        else:
            try:
                with conn() as c:
                    rid=c.execute('INSERT INTO recipes(name,yield_qty) VALUES(?,?)',(name.strip(),yield_qty)).lastrowid
                    c.executemany('INSERT INTO recipe_lines VALUES(?,?,?)',[(rid,iid,q) for iid,q in quantities.items() if q>0])
                st.success('Receta guardada');st.rerun()
            except sqlite3.IntegrityError:st.error('Ya existe una receta con ese nombre.')
elif page=='Inventario':
    display=it.copy();display['reservado']=display.id.map(reserved);display['disponible']=display.stock-display.reservado;display['valor_₡']=display.stock*display.cost;display['estado']=display.apply(lambda x:'PEDIR YA' if x.disponible<=x.min_stock else 'OK',axis=1)
    st.dataframe(display[['name','unit','stock','reservado','disponible','min_stock','cost','valor_₡','estado']],hide_index=True)
    st.subheader('Registrar compra')
    with st.form('buy'):
        selected=st.selectbox('Insumo',list(imap));qty=st.number_input('Cantidad recibida',min_value=0.01,value=100.0);unit_cost=st.number_input('Costo por unidad (₡)',min_value=0.0,value=float(it.loc[it.id==imap[selected],'cost'].iloc[0]));buy=st.form_submit_button('Registrar entrada')
    if buy:
        with conn() as c:
            c.execute('UPDATE items SET stock=stock+?,cost=? WHERE id=?',(qty,unit_cost,imap[selected]));c.execute('INSERT INTO movements(item_id,qty,type,reference,unit_cost) VALUES(?,?,?,?,?)',(imap[selected],qty,'Compra','Compra registrada',unit_cost))
        st.success('Compra registrada');st.rerun()
    with st.expander('Agregar ingrediente o empaque'):
        with st.form('item'):
            n=st.text_input('Nombre');u=st.selectbox('Unidad',['g','ml','unidad']);s=st.number_input('Existencia inicial',min_value=0.0);minimum=st.number_input('Stock mínimo',min_value=0.0);price=st.number_input('Costo por unidad ₡',min_value=0.0);save=st.form_submit_button('Guardar insumo')
        if save:
            try:
                with conn() as c:c.execute('INSERT INTO items(name,unit,stock,min_stock,cost) VALUES(?,?,?,?,?)',(n.strip(),u,s,minimum,price))
                st.rerun()
            except sqlite3.IntegrityError:st.error('Nombre duplicado.')
elif page=='Pedidos':
    st.subheader('Nuevo pedido')
    with st.form('order'):
        customer=st.text_input('Cliente');rname=st.selectbox('Receta',list(rmap));batches=st.number_input('Tandas',1,10000,1);process=st.date_input('Fecha de proceso',date.today());delivery=st.date_input('Fecha de entrega',date.today());price=st.number_input('Precio total de venta ₡',min_value=0.0);submit=st.form_submit_button('Guardar y reservar')
    if submit:
        if not customer.strip() or delivery<process:st.error('Indicá cliente y fechas válidas.')
        else:
            with conn() as c:c.execute('INSERT INTO orders(customer,recipe_id,batches,process_date,delivery_date,price) VALUES(?,?,?,?,?,?)',(customer.strip(),rmap[rname],batches,process.isoformat(),delivery.isoformat(),price))
            st.success('Pedido guardado. Insumos reservados (puede generar faltantes).');st.rerun()
    st.dataframe(query('SELECT o.id,o.customer,r.name producto,o.batches,o.process_date,o.delivery_date,o.price,o.status FROM orders o JOIN recipes r ON r.id=o.recipe_id ORDER BY o.id DESC'),hide_index=True)
elif page=='Producción':
    pending=query("SELECT o.id,o.customer,r.name,o.batches FROM orders o JOIN recipes r ON r.id=o.recipe_id WHERE o.status='Pendiente'")
    choices=['Sin pedido']+[f'#{r.id} · {r.customer} · {r.name} ({r.batches} tandas)' for r in pending.itertuples()]
    order_choice=st.selectbox('Pedido asociado',choices)
    order_id=None
    if order_choice!='Sin pedido':
        order_id=int(order_choice.split(' · ')[0][1:]);record=query('SELECT recipe_id,batches FROM orders WHERE id=?',(order_id,)).iloc[0]
        rid=int(record.recipe_id);batches=int(record.batches);rname=rs.loc[rs.id==rid,'name'].iloc[0]
        st.write(f'Receta: {rname} · {batches} tandas')
    else:
        rname=st.selectbox('Receta',list(rmap));rid=rmap[rname];batches=st.number_input('Tandas terminadas',1,10000,1)
    n=needs(rid,batches);n['disponible_para_esta_producción']=n.apply(lambda x:x.stock-reserved(x.id,order_id),axis=1)
    st.dataframe(n[['name','needed','unit','stock','disponible_para_esta_producción']],hide_index=True)
    st.write(f'**Costo estimado de ingredientes y empaques: ₡{cost(rid,batches):,.0f}**')
    enough=all(row.needed<=row.disponible_para_esta_producción for row in n.itertuples())
    if not enough:st.error('Insumos insuficientes o reservados para otros pedidos.')
    if st.button('Confirmar producción',disabled=not enough):
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            for row in n.itertuples():
                physical=c.execute('SELECT stock FROM items WHERE id=?',(int(row.id),)).fetchone()[0]
                other=c.execute('''SELECT COALESCE(SUM(rl.qty*o.batches),0) FROM orders o JOIN recipe_lines rl ON rl.recipe_id=o.recipe_id WHERE o.status='Pendiente' AND rl.item_id=? AND (? IS NULL OR o.id<>?)''',(int(row.id),order_id,order_id)).fetchone()[0]
                if physical-other<row.needed:raise ValueError('Stock cambió; revisá inventario.')
            for row in n.itertuples():
                c.execute('UPDATE items SET stock=stock-? WHERE id=?',(float(row.needed),int(row.id)))
                c.execute('INSERT INTO movements(item_id,qty,type,reference,unit_cost) VALUES(?,?,?,?,?)',(int(row.id),-float(row.needed),'Producción',f'Pedido {order_id}' if order_id else rname,float(row.cost)))
            if order_id:c.execute("UPDATE orders SET status='Producido' WHERE id=?",(order_id,))
        st.success('Producción registrada y stock descontado.');st.rerun()
elif page=='Movimientos y costos':
    st.subheader('Movimientos de inventario')
    st.dataframe(query('SELECT m.created_at,i.name insumo,m.type,m.qty,i.unit,m.unit_cost,m.reference FROM movements m JOIN items i ON i.id=m.item_id ORDER BY m.id DESC'),hide_index=True)
    st.subheader('Costo de insumos por receta')
    st.dataframe(pd.DataFrame([{'Receta':r.name,'Unidades por tanda':r.yield_qty,'Costo por tanda ₡':cost(r.id,1),'Costo por unidad ₡':cost(r.id,1)/r.yield_qty} for r in rs.itertuples()]),hide_index=True)
    st.caption('Costos estimados de ingredientes y empaques; no incluyen mano de obra, electricidad ni gastos indirectos. El prototipo usa costo unitario actual, no costo histórico por lote.')
