import csv

class AverageMeter():

    def __init__(self):
        self.reset()

    def reset(self):
        self.val = 0.
        self.avg = 0.
        self.sum = 0.
        self.count = 0.
        self.min, self.max = 0., 0.

    def update(self, value, step: int=1):
        if self.count == 0:
            self.min = self.max = value
        else:
            if value < self.min: self.min = value
            if value > self.max: self.max = value
        self.val += value
        self.sum += value * step
        self.count += step
        self.avg = self.sum / self.count
        
class csv_logger():

    def __init__(self, path, header):
       
        file = open(path, 'w', newline='')
        self.writer = csv.writer(file)
        if len(header) > 0:
            self.writer.writerow(header)

    def writerow(self, row):
        self.writer.writerow(row)