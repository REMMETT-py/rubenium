-- 8.0: a swap's id and file name are plain names, so the app can never be made to write outside its folder.
begin;
do $$ begin
    insert into public.rb_swaps (id, cat, old, new, file) values ('octane_gold', 'body', 'a', 'b', 'Body_Octane_SF.upk');
    assert t.try($q$insert into public.rb_swaps (id, cat, old, new, file) values ('../../x', 'body', 'a', 'b', 'Body.upk')$q$) <> '', 'id with ..';
    assert t.try($q$insert into public.rb_swaps (id, cat, old, new, file) values ('ok2', 'body', 'a', 'b', '..\evil.upk')$q$) <> '', 'file with ..\';
    assert t.try($q$insert into public.rb_swaps (id, cat, old, new, file) values ('ok3', 'body', 'a', 'b', 'a/b.upk')$q$) <> '', 'file with a folder';
    assert t.try($q$insert into public.rb_swaps (id, cat, old, new, file) values ('ok4', 'body', 'a', 'b', 'run.exe')$q$) <> '', 'an .exe';
    assert t.try($q$insert into public.rb_swaps (id, cat, old, new, file) values ('_originals', 'body', 'a', 'b', 'x.upk')$q$) <> '', 'the originals folder';
end $$;
rollback;
