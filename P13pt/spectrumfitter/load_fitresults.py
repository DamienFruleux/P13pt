from P13pt.params_from_filename import params_from_filename

def load_fitresults(filename, readfilenameparams=True, extrainfo=False):
    dummy = thru = dut = ra = model = None
    fitter_info = {}
    # read results file
    with open(filename, 'r') as f:
        # read the header
        column_header = None
        previous_line = None
        end_of_header = False
        data = []
        for line in f:
            line = line.strip()
            if line:
                if line[0] == '#':  # line is a comment line
                    line = line[1:].strip()
                    if line.startswith('thru:'):
                        thru = line[5:].strip()
                    elif line.startswith('dummy:'):
                        dummy = line[6:].strip()
                    elif line.startswith('dut:'):
                        dut = line[4:].strip()
                    elif line.startswith('ra:'):
                        ra = float(line[3:].strip())
                    # TODO: this dictionary could be automatically generated (more elegant)
                    elif line.startswith('model:'):
                        fitter_info['model'] = line[6:].strip()
                    elif line.startswith('fitted_param:'):
                        fitter_info['fitted_param'] = line[13:].strip()
                    elif line.startswith('model_func:'):
                        fitter_info['model_func'] = line[11:].strip()
                    elif line.startswith('fit_method:'):
                        fitter_info['fit_method'] = line[11:].strip()
                else:
                    # check if we reached the end of the header (or if we already had reached it previously)
                    # and if there is a last header line
                    if not end_of_header:
                        end_of_header = True
                        if previous_line:  # '#' was removed already
                            column_header = previous_line.split('\t')
                    data.append(line.split('\t'))
                previous_line = line
        data = list(zip(*data))  # transpose array, the list(...) is for python 3

        # remove file name parameter columns if requested
        # (only try this if a column_header was detected)
        if column_header and not readfilenameparams:
            if not column_header[0] == 'filename':
                return None
            if not len(data):
                return None
            num_params = len(params_from_filename(data[0][0]))
            data = [data[0]]+data[num_params+1:]
            column_header = [column_header[0]]+column_header[num_params+1:]

        # put everything together
        if column_header and len(column_header) == len(data):
            data = dict(zip(column_header, data))
        else:
            data = None

    if not extrainfo:
        return data
    else:
        return data, dut, thru, dummy, ra, fitter_info
