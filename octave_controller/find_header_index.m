function idx = find_header_index(headers, name)
  % finds a required header name (case-insensitive)
  idx = find(strcmpi(strtrim(headers), name), 1);
  if isempty(idx)
    error('Required column not found: %s', name);
  end
end
