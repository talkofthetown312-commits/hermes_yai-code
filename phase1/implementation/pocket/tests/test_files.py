"""Attachment security/format tests use only isolated temporary conversations."""
import base64
import io
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile
import test_bridge as bridge_tests
from pocket_files import decode_upload, extract_text, MAX_FILE, safe_read


def encoded(name,raw): return {'name':name,'data':base64.b64encode(raw).decode()}


def office(files):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        for name,text in files.items(): z.writestr(name,text)
    return stream.getvalue()


class FileFormats(unittest.TestCase):
    def test_filename_encoding_type_and_size_rejections(self):
        for name,raw in [('../x.txt',b'x'),('x\\y.txt',b'x'),('bad\n.txt',b'x'),('x.apk',b'x'),('x.txt',b''),('x.png',b'not an image'),('x.pdf',b'not pdf')]:
            with self.subTest(name=name),self.assertRaises(ValueError): decode_upload(encoded(name,raw))
        with self.assertRaises(ValueError):decode_upload({'name':'x.txt','data':'bad@@'})
        with self.assertRaises(ValueError):decode_upload({'name':'x.txt','data':'A'*(MAX_FILE*2)})
    def test_text_and_html_are_plain_text(self):
        for name in ['x.txt','x.html','x.csv','x.py']:
            self.assertEqual(extract_text(name,b'<script>bad()</script>'),'<script>bad()</script>')
        self.assertIn('TRUNCATED',extract_text('x.txt',b'1234567890',4))
        with self.assertRaises(ValueError):extract_text('x.txt',b'\xff')
        with self.assertRaises(ValueError):extract_text('x.txt',b'a\x00b')
    def test_docx_text_and_entity_rejection(self):
        raw=office({'word/document.xml':'<w:document xmlns:w="urn:test"><w:p><w:r><w:t>Invoice 42</w:t></w:r></w:p></w:document>'})
        self.assertEqual(extract_text('sample.docx',raw),'Invoice 42')
        raw=office({'word/document.xml':'<!DOCTYPE x [<!ENTITY e "bad">]><x>&e;</x>'})
        with self.assertRaises(ValueError):extract_text('sample.docx',raw)
    def test_xlsx_shared_inline_and_numeric_cells(self):
        raw=office({'xl/sharedStrings.xml':'<sst xmlns="urn:test"><si><t>Sales</t></si></sst>', 'xl/worksheets/sheet1.xml':'<sheet xmlns="urn:test"><row><c t="s"><v>0</v></c><c><v>17</v></c><c t="inlineStr"><is><t>Total</t></is></c></row></sheet>'})
        self.assertIn('Sales\t17\tTotal',extract_text('sample.xlsx',raw))
    def test_text_pdf_extraction(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        writer=PdfWriter();page=writer.add_blank_page(width=200,height=200)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 14 Tf 20 100 Td (Synthetic invoice 73) Tj ET')
        page[NameObject('/Contents')]=writer._add_object(stream)
        out=io.BytesIO();writer.write(out)
        self.assertIn('Synthetic invoice 73',extract_text('invoice.pdf',out.getvalue()))
    def test_scanned_and_encrypted_pdf_errors(self):
        from pypdf import PdfWriter
        for encrypted in (False,True):
            writer=PdfWriter();writer.add_blank_page(width=100,height=100)
            if encrypted: writer.encrypt('synthetic-password')
            data=io.BytesIO();writer.write(data)
            with self.subTest(encrypted=encrypted),self.assertRaises(ValueError):extract_text('x.pdf',data.getvalue())
    def test_raster_image_validation(self):
        from PIL import Image
        data=io.BytesIO();Image.new('RGB',(8,8),'green').save(data,format='PNG')
        name,mime,raw=decode_upload(encoded('photo.png',data.getvalue()))
        self.assertEqual(mime,'image/png')
        with self.assertRaises(ValueError):decode_upload(encoded('photo.jpg',raw))


class AttachmentAPI(unittest.TestCase):
    setUpClass=classmethod(bridge_tests.BridgeTest.setUpClass.__func__)
    tearDownClass=classmethod(bridge_tests.BridgeTest.tearDownClass.__func__)
    req=bridge_tests.BridgeTest.req
    wait_chat=bridge_tests.BridgeTest.wait_chat
    def chat(self,mode='cloud'):return self.req('chats',{'mode':mode,'model':'test-model'})['id']
    def upload(self,cid,name='notes.txt',raw=b'fixture-content'):return self.req('files/upload',{'chat':cid,**encoded(name,raw)})
    def content(self,cid,fid):return self.req('files/'+fid+'?chat='+cid)
    def test_auth_origin_upload_and_private_reads(self):
        cid=self.chat()
        with self.assertRaises(urllib.error.HTTPError) as e:self.req('files/upload',{'chat':cid,**encoded('x.txt',b'x')},token=False)
        self.assertEqual(e.exception.code,401)
        with self.assertRaises(urllib.error.HTTPError) as e:self.req('files/upload',{'chat':cid,**encoded('x.txt',b'x')},origin='https://evil.example')
        self.assertEqual(e.exception.code,403)
        f=self.upload(cid);out=self.content(cid,f['id'])
        self.assertEqual(base64.b64decode(out['data']),b'fixture-content')
        self.assertEqual(out['preview'],'fixture-content');self.assertNotIn('path',out)
        with self.assertRaises(urllib.error.HTTPError):self.content(self.chat(),f['id'])
        with self.assertRaises(urllib.error.HTTPError):self.req('files/'+f['id']+'?chat='+cid,token=False)
    def test_draft_attachment_recovery(self):
        cid=self.chat();f=self.upload(cid)
        self.assertEqual([x['id'] for x in self.req('drafts?chat='+cid)],[f['id']])
        self.b.save(cid,[{'role':'user','text':'sent','attachments':[f]}],'session','idle')
        self.assertEqual(self.req('drafts?chat='+cid),[])
    def test_upload_remove_and_used_file_protection(self):
        cid=self.chat();f=self.upload(cid)
        self.req('files/remove',{'chat':cid,'id':f['id']})
        with self.assertRaises(urllib.error.HTTPError):self.content(cid,f['id'])
        f=self.upload(cid);chat=self.b.read_chat(cid)
        self.b.save(cid,[{'role':'user','text':'x','attachments':[f]}],None,'idle')
        with self.assertRaises(urllib.error.HTTPError):self.req('files/remove',{'chat':cid,'id':f['id']})
    def test_prepare_ids_local_limits_and_cloud_consent(self):
        cid=self.chat();f=self.upload(cid)
        for ids in [[f['id'],f['id']],['missing'],[{}]]:
            with self.subTest(ids=ids),self.assertRaises(ValueError):self.b.FILES.prepare(cid,ids,'cloud')
        old=self.b.CAPABILITY;self.b.CAPABILITY={'ready':True,'adapter':'installed-hermes-sdk'}
        try:
            with self.assertRaises(urllib.error.HTTPError) as e:self.req('send',{'id':cid,'message':'read','attachments':[f['id']]})
            self.assertEqual(e.exception.code,400)
            self.assertEqual(self.b.read_chat(cid)['messages'],[])
            event=threading.Event();seen={}
            def fake_turn(chat_id,prompt,smoke,text,images):
                seen.update(prompt=prompt,text=text,images=images)
                chat=self.b.read_chat(chat_id)
                self.b.save(chat_id,chat['messages'],'fixture-session','idle')
                with self.b.LOCK:self.b.RUNNING.discard(chat_id)
                event.set()
            with patch.object(self.b,'run_turn',fake_turn):
                self.req('send',{'id':cid,'message':'read','attachments':[f['id']],'consent':True})
                self.assertTrue(event.wait(3))
            self.assertIn('fixture-content',seen['text']);self.assertEqual(seen['images'],[])
            self.assertEqual(self.b.read_chat(cid)['messages'][0]['attachments'][0]['id'],f['id'])
        finally:self.b.CAPABILITY=old
    def test_local_photo_rejection_no_cloud_fallback(self):
        from PIL import Image
        data=io.BytesIO();Image.new('RGB',(8,8),'red').save(data,format='PNG')
        cid=self.chat('local');f=self.upload(cid,'photo.png',data.getvalue())
        with self.assertRaisesRegex(ValueError,'cannot analyse'):self.b.FILES.prepare(cid,[f['id']],'local')
    def test_workspace_outputs_ownership_symlinks_and_traversal(self):
        cid=self.chat();out=self.b.FILES.workspace(cid)/'outputs'
        (out/'report.csv').write_text('item,total\nfixture,7\n')
        (out/'private-link.txt').symlink_to(Path(self.temp.name)/'pairing-token')
        files=self.req('artifacts?chat='+cid)
        self.assertEqual([f['name'] for f in files],['report.csv'])
        result=self.content(cid,files[0]['id']);self.assertIn(b'fixture,7',base64.b64decode(result['data']))
        with self.assertRaises(urllib.error.HTTPError):self.content(self.chat(),files[0]['id'])
        with self.assertRaises(ValueError):safe_read(out/'private-link.txt',out)
        for name in ['../escape.txt','x/y.txt','x\\y.txt']:
            with self.subTest(name=name),self.assertRaises(urllib.error.HTTPError):self.upload(cid,name,b'x')
    def test_quota_and_unsupported_file(self):
        cid=self.chat()
        with patch('pocket_files.MAX_STORAGE',2):
            with self.assertRaises(urllib.error.HTTPError):self.upload(cid)
        with self.assertRaises(urllib.error.HTTPError):self.upload(cid,'x.exe',b'MZ')


if __name__=='__main__':unittest.main()
